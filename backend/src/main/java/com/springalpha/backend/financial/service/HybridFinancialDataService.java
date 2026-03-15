package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.cache.MarketDataCacheService;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

@Service
@Primary
public class HybridFinancialDataService implements FinancialDataService {

    private static final Logger log = LoggerFactory.getLogger(HybridFinancialDataService.class);
    private static final String CACHE_SOURCE = "hybrid-v5-sec-report-date";

    private final SecCompanyFactsFinancialDataService secFinancialDataService;
    private final MarketEnrichmentService marketEnrichmentService;
    private final MarketDataCacheService cacheService;
    private final Duration factsCacheTtl;
    private final Duration historyCacheTtl;
    private final ConcurrentHashMap<String, CompletableFuture<?>> inFlightRequests = new ConcurrentHashMap<>();

    @Autowired
    public HybridFinancialDataService(
            SecCompanyFactsFinancialDataService secFinancialDataService,
            MarketEnrichmentService marketEnrichmentService,
            MarketDataCacheService cacheService,
            @Value("${app.hybrid.cache.facts-ttl:PT6H}") Duration factsCacheTtl,
            @Value("${app.hybrid.cache.history-ttl:PT24H}") Duration historyCacheTtl) {
        this.secFinancialDataService = secFinancialDataService;
        this.marketEnrichmentService = marketEnrichmentService;
        this.cacheService = cacheService;
        this.factsCacheTtl = factsCacheTtl;
        this.historyCacheTtl = historyCacheTtl;
    }

    @Override
    public FinancialFacts getFinancialFacts(String ticker) {
        return getFinancialFacts(ticker, "quarterly");
    }

    @Override
    public FinancialFacts getFinancialFacts(String ticker, String reportType) {
        String upperTicker = ticker.toUpperCase();
        String normalizedReportType = normalizeReportType(reportType);

        Optional<FinancialFacts> cachedFacts = cacheService == null
                ? Optional.empty()
                : cacheService.getFinancialFacts(CACHE_SOURCE, upperTicker, normalizedReportType, false);
        if (cachedFacts.isPresent()) {
            FinancialFacts facts = cachedFacts.get();
            boolean reconciledDashboardMode = reconcileDashboardModeFromExistingMetadata(facts);
            boolean needsMetadataBackfill = needsMarketMetadataBackfill(facts);
            boolean needsQuarterlyFactsBackfill = needsQuarterlyFactsBackfill(facts);
            if (needsMetadataBackfill || needsQuarterlyFactsBackfill) {
                log.info("♻️ Backfilling cached facts for {} ({}) [metadata={}, quarterly={}]",
                        upperTicker,
                        normalizedReportType,
                        needsMetadataBackfill,
                        needsQuarterlyFactsBackfill);
                enrichWithMarketData(facts, upperTicker, normalizedReportType);
            }
            if (reconciledDashboardMode || needsMetadataBackfill || needsQuarterlyFactsBackfill) {
                cacheFinancialFacts(upperTicker, normalizedReportType, facts);
            }
            return facts;
        }

        try {
            return executeDeduped(buildFactsCacheKey(upperTicker, normalizedReportType),
                    () -> loadFinancialFacts(upperTicker, normalizedReportType));
        } catch (Exception e) {
            log.warn("⚠️ Failed to resolve hybrid financial facts for {} ({}): {}", upperTicker, normalizedReportType,
                    e.getMessage());
            return null;
        }
    }

    @Override
    public List<HistoricalDataPoint> getHistoricalData(String ticker) {
        return getHistoricalData(ticker, "quarterly");
    }

    @Override
    public List<HistoricalDataPoint> getHistoricalData(String ticker, String reportType) {
        String upperTicker = ticker.toUpperCase();
        String normalizedReportType = normalizeReportType(reportType);

        Optional<List<HistoricalDataPoint>> cachedHistory = cacheService == null
                ? Optional.empty()
                : cacheService.getHistoricalData(CACHE_SOURCE, upperTicker, normalizedReportType, false);
        if (cachedHistory.isPresent()) {
            List<HistoricalDataPoint> history = cachedHistory.get();
            if (needsQuarterlyHistoryBackfill(history)) {
                log.info("♻️ Backfilling quarterly chart data for cached history: {} ({})", upperTicker,
                        normalizedReportType);
                enrichHistoryWithMarketData(history, upperTicker, normalizedReportType);
                cacheHistoricalData(upperTicker, normalizedReportType, history);
            }
            return history;
        }

        try {
            return executeDeduped(buildHistoryCacheKey(upperTicker, normalizedReportType),
                    () -> loadHistoricalData(upperTicker, normalizedReportType));
        } catch (Exception e) {
            log.warn("⚠️ Failed to resolve hybrid history for {} ({}): {}", upperTicker, normalizedReportType,
                    e.getMessage());
            return Collections.emptyList();
        }
    }

    @Override
    public boolean isSupported(String ticker) {
        return secFinancialDataService.isSupported(ticker);
    }

    @Override
    public String[] getSupportedTickers() {
        return secFinancialDataService.getSupportedTickers();
    }

    private FinancialFacts loadFinancialFacts(String upperTicker, String reportType) {
        FinancialFacts facts = secFinancialDataService.getFinancialFacts(upperTicker, reportType);
        if (facts != null) {
            enrichWithMarketData(facts, upperTicker, reportType);
            cacheFinancialFacts(upperTicker, reportType, facts);
            return facts;
        }

        FinancialFacts fallbackFacts = buildUnsupportedTickerFallback(upperTicker, reportType);
        if (fallbackFacts != null) {
            cacheFinancialFacts(upperTicker, reportType, fallbackFacts);
            return fallbackFacts;
        }

        log.warn("⚠️ SEC core financial facts unavailable for {}. Main analysis path will stop here.", upperTicker);
        return null;
    }

    private List<HistoricalDataPoint> loadHistoricalData(String upperTicker, String reportType) {
        List<HistoricalDataPoint> history = secFinancialDataService.getHistoricalData(upperTicker, reportType);
        if (history != null && !history.isEmpty()) {
            enrichHistoryWithMarketData(history, upperTicker, reportType);
            cacheHistoricalData(upperTicker, reportType, history);
            return history;
        }

        log.warn("⚠️ SEC historical data unavailable for {}. Returning empty history.", upperTicker);
        return Collections.emptyList();
    }

    private void enrichWithMarketData(FinancialFacts facts, String ticker, String reportType) {
        if (marketEnrichmentService == null) {
            return;
        }
        try {
            MarketSupplementalData supplementalData = marketEnrichmentService.getSupplementalData(ticker, reportType);
            log.info("📦 Market enrichment for {} ({}) returned profile={}, quote={}, valuation={}, quarterlySnapshots={}",
                    ticker,
                    reportType,
                    supplementalData.profileAvailable(),
                    supplementalData.quoteAvailable(),
                    supplementalData.valuationAvailable(),
                            supplementalData.quarterlyFinancials() == null ? 0 : supplementalData.quarterlyFinancials().size());
            applyQuarterlyFinancialFallbacks(facts, supplementalData);

            if (isBlank(facts.getCompanyName()) && !isBlank(supplementalData.companyName())) {
                facts.setCompanyName(supplementalData.companyName());
            }
            if (!isBlank(supplementalData.sector())) {
                facts.setMarketSector(supplementalData.sector());
            }
            if (!isBlank(supplementalData.industry())) {
                facts.setMarketIndustry(supplementalData.industry());
            }
            if (!isBlank(supplementalData.securityType())) {
                facts.setMarketSecurityType(supplementalData.securityType());
            }
            if (isBlank(facts.getMarketBusinessSummary()) && !isBlank(supplementalData.businessSummary())) {
                facts.setMarketBusinessSummary(supplementalData.businessSummary());
            }

            if (supplementalData.priceToEarningsRatio() != null) {
                facts.setPriceToEarningsRatio(supplementalData.priceToEarningsRatio());
            } else if (!"quarterly".equalsIgnoreCase(reportType)
                    && supplementalData.latestPrice() != null && facts.getEarningsPerShare() != null
                    && facts.getEarningsPerShare().compareTo(BigDecimal.ZERO) > 0) {
                facts.setPriceToEarningsRatio(
                        supplementalData.latestPrice().divide(facts.getEarningsPerShare(), 4, RoundingMode.HALF_UP));
            }

            if (supplementalData.priceToBookRatio() != null) {
                facts.setPriceToBookRatio(supplementalData.priceToBookRatio());
            } else if (supplementalData.marketCap() != null
                    && facts.getTotalEquity() != null
                    && facts.getTotalEquity().compareTo(BigDecimal.ZERO) > 0) {
                facts.setPriceToBookRatio(
                        supplementalData.marketCap().divide(facts.getTotalEquity(), 4, RoundingMode.HALF_UP));
            }

            if (hasMarketClassificationInputs(supplementalData)) {
                DashboardModeClassifier.DashboardMode dashboardMode = DashboardModeClassifier.classify(facts,
                        supplementalData);
                facts.setDashboardMode(dashboardMode.mode());
                facts.setDashboardMessage(dashboardMode.message());
            }
        } catch (Exception e) {
            log.warn("⚠️ Market enrichment failed for {}: {}", ticker, e.getMessage());
        }
    }

    private void enrichHistoryWithMarketData(List<HistoricalDataPoint> history, String ticker, String reportType) {
        if (marketEnrichmentService == null || history == null || history.isEmpty()) {
            return;
        }

        try {
            MarketSupplementalData supplementalData = marketEnrichmentService.getSupplementalData(ticker, reportType);
            if (supplementalData.quarterlyFinancials() == null || supplementalData.quarterlyFinancials().isEmpty()) {
                return;
            }

            for (HistoricalDataPoint point : history) {
                MarketSupplementalData.QuarterlyFinancialSnapshot snapshot = matchQuarterlySnapshot(
                        point.getRevenue(),
                        point.getNetIncome(),
                        supplementalData.quarterlyFinancials());
                if (snapshot == null) {
                    log.debug("🟡 No Yahoo quarterly snapshot matched history point {} for {}", point.getPeriod(), ticker);
                    continue;
                }

                if (point.getRevenue() == null && snapshot.revenue() != null) {
                    point.setRevenue(snapshot.revenue());
                }
                if (point.getNetIncome() == null && snapshot.netIncome() != null) {
                    point.setNetIncome(snapshot.netIncome());
                }
                if (point.getGrossMargin() == null && snapshot.grossProfit() != null) {
                    point.setGrossMargin(divide(snapshot.grossProfit(), point.getRevenue()));
                }
                if (point.getOperatingMargin() == null && snapshot.operatingIncome() != null) {
                    point.setOperatingMargin(divide(snapshot.operatingIncome(), point.getRevenue()));
                }
                if (point.getNetMargin() == null && snapshot.netIncome() != null) {
                    point.setNetMargin(divide(snapshot.netIncome(), point.getRevenue()));
                }
            }
        } catch (Exception e) {
            log.warn("⚠️ Market history enrichment failed for {}: {}", ticker, e.getMessage());
        }
    }

    private void applyQuarterlyFinancialFallbacks(FinancialFacts facts, MarketSupplementalData supplementalData) {
        if (facts == null || supplementalData == null
                || supplementalData.quarterlyFinancials() == null
                || supplementalData.quarterlyFinancials().isEmpty()) {
            return;
        }

        MarketSupplementalData.QuarterlyFinancialSnapshot snapshot = matchQuarterlySnapshot(
                facts.getRevenue(),
                facts.getNetIncome(),
                supplementalData.quarterlyFinancials());
        if (snapshot == null) {
            log.info("🟡 No Yahoo quarterly snapshot matched facts for {} (revenue={}, netIncome={})",
                    facts.getTicker(),
                    facts.getRevenue(),
                    facts.getNetIncome());
            return;
        }

        log.info("✅ Matched Yahoo quarterly snapshot {} for {} (revenue={}, netIncome={})",
                snapshot.periodEnd(),
                facts.getTicker(),
                snapshot.revenue(),
                snapshot.netIncome());

        if (facts.getRevenue() == null && snapshot.revenue() != null) {
            facts.setRevenue(snapshot.revenue());
        }
        if (facts.getGrossProfit() == null && snapshot.grossProfit() != null) {
            facts.setGrossProfit(snapshot.grossProfit());
        }
        if (facts.getGrossMargin() == null && snapshot.grossProfit() != null) {
            facts.setGrossMargin(divide(snapshot.grossProfit(), facts.getRevenue()));
        }
        if (facts.getOperatingIncome() == null && snapshot.operatingIncome() != null) {
            facts.setOperatingIncome(snapshot.operatingIncome());
        }
        if (facts.getOperatingMargin() == null && snapshot.operatingIncome() != null) {
            facts.setOperatingMargin(divide(snapshot.operatingIncome(), facts.getRevenue()));
        }
        if (facts.getNetIncome() == null && snapshot.netIncome() != null) {
            facts.setNetIncome(snapshot.netIncome());
        }
        if (facts.getNetMargin() == null && snapshot.netIncome() != null) {
            facts.setNetMargin(divide(snapshot.netIncome(), facts.getRevenue()));
        }
        if (facts.getOperatingCashFlow() == null && snapshot.operatingCashFlow() != null) {
            facts.setOperatingCashFlow(snapshot.operatingCashFlow());
        }
        if (facts.getFreeCashFlow() == null && snapshot.freeCashFlow() != null) {
            facts.setFreeCashFlow(snapshot.freeCashFlow());
        }

        applyQuarterlyGrowthFallbacks(facts, snapshot, supplementalData.quarterlyFinancials());
    }

    private FinancialFacts buildUnsupportedTickerFallback(String ticker, String reportType) {
        if (marketEnrichmentService == null) {
            return null;
        }

        try {
            MarketSupplementalData supplementalData = marketEnrichmentService.getSupplementalData(ticker, reportType);
            DashboardModeClassifier.DashboardMode dashboardMode = DashboardModeClassifier.classify(null, supplementalData);
            if (!dashboardMode.isUnsupportedReit()) {
                return null;
            }

            log.info("🛑 Returning market-only fallback facts for unsupported REIT {} because SEC core facts were unavailable.",
                    ticker);
            return FinancialFacts.builder()
                    .ticker(ticker)
                    .companyName(firstNonBlank(supplementalData.companyName(), ticker))
                    .marketSector(supplementalData.sector())
                    .marketIndustry(supplementalData.industry())
                    .marketSecurityType(supplementalData.securityType())
                    .marketBusinessSummary(supplementalData.businessSummary())
                    .priceToEarningsRatio(supplementalData.priceToEarningsRatio())
                    .priceToBookRatio(supplementalData.priceToBookRatio())
                    .dashboardMode(dashboardMode.mode())
                    .dashboardMessage(dashboardMode.message())
                    .build();
        } catch (Exception e) {
            log.warn("⚠️ Market fallback classification failed for {}: {}", ticker, e.getMessage());
            return null;
        }
    }

    private String firstNonBlank(String preferred, String fallback) {
        if (preferred != null && !preferred.isBlank()) {
            return preferred;
        }
        return fallback;
    }

    private MarketSupplementalData.QuarterlyFinancialSnapshot matchQuarterlySnapshot(
            BigDecimal revenue,
            BigDecimal netIncome,
            List<MarketSupplementalData.QuarterlyFinancialSnapshot> snapshots) {
        if (snapshots == null || snapshots.isEmpty()) {
            return null;
        }

        MarketSupplementalData.QuarterlyFinancialSnapshot best = null;
        BigDecimal bestScore = null;

        for (MarketSupplementalData.QuarterlyFinancialSnapshot snapshot : snapshots) {
            if (snapshot == null) {
                continue;
            }

            boolean hasRevenueAnchor = revenue != null
                    && revenue.compareTo(BigDecimal.ZERO) != 0
                    && snapshot.revenue() != null;
            boolean hasNetIncomeAnchor = netIncome != null
                    && netIncome.compareTo(BigDecimal.ZERO) != 0
                    && snapshot.netIncome() != null;
            if (!hasRevenueAnchor && !hasNetIncomeAnchor) {
                continue;
            }

            BigDecimal score = BigDecimal.ZERO;
            if (hasRevenueAnchor) {
                BigDecimal revenueDistance = snapshot.revenue().subtract(revenue).abs()
                        .divide(revenue.abs(), 6, RoundingMode.HALF_UP);
                if (revenueDistance.compareTo(new BigDecimal("0.03")) > 0) {
                    continue;
                }
                score = score.add(revenueDistance);
            }
            if (hasNetIncomeAnchor) {
                BigDecimal netIncomeDistance = snapshot.netIncome().subtract(netIncome).abs()
                        .divide(netIncome.abs(), 6, RoundingMode.HALF_UP);
                if (!hasRevenueAnchor && netIncomeDistance.compareTo(new BigDecimal("0.05")) > 0) {
                    continue;
                }
                score = score.add(hasRevenueAnchor
                        ? netIncomeDistance.divide(new BigDecimal("10"), 6, RoundingMode.HALF_UP)
                        : netIncomeDistance);
            }

            if (bestScore == null || score.compareTo(bestScore) < 0) {
                best = snapshot;
                bestScore = score;
            }
        }

        return best;
    }

    private void applyQuarterlyGrowthFallbacks(
            FinancialFacts facts,
            MarketSupplementalData.QuarterlyFinancialSnapshot currentSnapshot,
            List<MarketSupplementalData.QuarterlyFinancialSnapshot> snapshots) {
        if (facts == null || currentSnapshot == null || snapshots == null || snapshots.isEmpty()) {
            return;
        }

        MarketSupplementalData.QuarterlyFinancialSnapshot previousYearSnapshot = findPreviousYearSnapshot(
                currentSnapshot,
                snapshots);
        if (previousYearSnapshot == null) {
            return;
        }

        if (facts.getRevenueYoY() == null && facts.getRevenue() != null && previousYearSnapshot.revenue() != null) {
            facts.setRevenueYoY(calculateGrowthRate(previousYearSnapshot.revenue(), facts.getRevenue()));
        }
        if (facts.getOperatingCashFlowYoY() == null
                && facts.getOperatingCashFlow() != null
                && previousYearSnapshot.operatingCashFlow() != null) {
            facts.setOperatingCashFlowYoY(calculateGrowthRate(
                    previousYearSnapshot.operatingCashFlow(),
                    facts.getOperatingCashFlow()));
        }
        if (facts.getFreeCashFlowYoY() == null
                && facts.getFreeCashFlow() != null
                && previousYearSnapshot.freeCashFlow() != null) {
            facts.setFreeCashFlowYoY(calculateGrowthRate(
                    previousYearSnapshot.freeCashFlow(),
                    facts.getFreeCashFlow()));
        }
    }

    private MarketSupplementalData.QuarterlyFinancialSnapshot findPreviousYearSnapshot(
            MarketSupplementalData.QuarterlyFinancialSnapshot currentSnapshot,
            List<MarketSupplementalData.QuarterlyFinancialSnapshot> snapshots) {
        LocalDate currentDate = parsePeriodEnd(currentSnapshot.periodEnd());
        if (currentDate == null) {
            return null;
        }

        MarketSupplementalData.QuarterlyFinancialSnapshot best = null;
        long bestDistance = Long.MAX_VALUE;
        for (MarketSupplementalData.QuarterlyFinancialSnapshot snapshot : snapshots) {
            if (snapshot == null || Objects.equals(snapshot.periodEnd(), currentSnapshot.periodEnd())) {
                continue;
            }
            LocalDate candidateDate = parsePeriodEnd(snapshot.periodEnd());
            if (candidateDate == null || !candidateDate.isBefore(currentDate)) {
                continue;
            }
            long days = Math.abs(java.time.temporal.ChronoUnit.DAYS.between(candidateDate, currentDate));
            if (days < 300 || days > 430) {
                continue;
            }
            if (days < bestDistance) {
                best = snapshot;
                bestDistance = days;
            }
        }
        return best;
    }

    private LocalDate parsePeriodEnd(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(value);
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }

    private BigDecimal divide(BigDecimal numerator, BigDecimal denominator) {
        if (numerator == null || denominator == null || denominator.compareTo(BigDecimal.ZERO) == 0) {
            return null;
        }
        return numerator.divide(denominator, 4, RoundingMode.HALF_UP);
    }

    private BigDecimal calculateGrowthRate(BigDecimal previous, BigDecimal current) {
        if (previous == null || current == null || previous.compareTo(BigDecimal.ZERO) == 0) {
            return null;
        }
        return current.subtract(previous)
                .divide(previous.abs(), 4, RoundingMode.HALF_UP);
    }

    private void cacheFinancialFacts(String ticker, String reportType, FinancialFacts facts) {
        if (cacheService != null && facts != null) {
            cacheService.putFinancialFacts(CACHE_SOURCE, ticker, reportType, facts, factsCacheTtl);
        }
    }

    private boolean needsMarketMetadataBackfill(FinancialFacts facts) {
        if (facts == null) {
            return false;
        }
        return isBlank(facts.getDashboardMode())
                || isBlank(facts.getMarketSector())
                || isBlank(facts.getMarketIndustry())
                || isBlank(facts.getMarketSecurityType())
                || isBlank(facts.getMarketBusinessSummary());
    }

    private boolean needsQuarterlyHistoryBackfill(List<HistoricalDataPoint> history) {
        if (history == null || history.isEmpty()) {
            return false;
        }
        return history.stream().anyMatch(point ->
                point != null
                        && point.getRevenue() == null
                        && point.getNetIncome() != null);
    }

    private boolean needsQuarterlyFactsBackfill(FinancialFacts facts) {
        if (facts == null) {
            return false;
        }
        return facts.getRevenue() == null && facts.getNetIncome() != null;
    }

    private boolean reconcileDashboardModeFromExistingMetadata(FinancialFacts facts) {
        if (facts == null) {
            return false;
        }

        MarketSupplementalData cachedMetadata = new MarketSupplementalData(
                "cache",
                false,
                false,
                false,
                facts.getCompanyName(),
                facts.getMarketSector(),
                facts.getMarketIndustry(),
                facts.getMarketSecurityType(),
                null,
                null,
                null,
                null,
                List.of(),
                null,
                facts.getMarketBusinessSummary());
        if (!hasMarketClassificationInputs(cachedMetadata)) {
            return false;
        }

        DashboardModeClassifier.DashboardMode expectedMode = DashboardModeClassifier.classify(facts, cachedMetadata);
        if (Objects.equals(normalizeBlank(facts.getDashboardMode()), normalizeBlank(expectedMode.mode()))
                && Objects.equals(normalizeBlank(facts.getDashboardMessage()), normalizeBlank(expectedMode.message()))) {
            return false;
        }

        facts.setDashboardMode(expectedMode.mode());
        facts.setDashboardMessage(expectedMode.message());
        return true;
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String normalizeBlank(String value) {
        return isBlank(value) ? null : value;
    }

    private boolean hasMarketClassificationInputs(MarketSupplementalData supplementalData) {
        if (supplementalData == null) {
            return false;
        }
        return !isBlank(supplementalData.companyName())
                || !isBlank(supplementalData.sector())
                || !isBlank(supplementalData.industry())
                || !isBlank(supplementalData.securityType());
    }

    private void cacheHistoricalData(String ticker, String reportType, List<HistoricalDataPoint> history) {
        if (cacheService != null && history != null && !history.isEmpty()) {
            cacheService.putHistoricalData(CACHE_SOURCE, ticker, reportType, history, historyCacheTtl);
        }
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private String buildFactsCacheKey(String ticker, String reportType) {
        return CACHE_SOURCE + ":facts:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String buildHistoryCacheKey(String ticker, String reportType) {
        return CACHE_SOURCE + ":history:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    @SuppressWarnings("unchecked")
    private <T> T executeDeduped(String cacheKey, java.util.function.Supplier<T> supplier) {
        CompletableFuture<T> created = new CompletableFuture<>();
        CompletableFuture<T> existing = (CompletableFuture<T>) inFlightRequests.putIfAbsent(cacheKey, created);
        if (existing != null) {
            return existing.join();
        }

        try {
            T result = supplier.get();
            created.complete(result);
            return result;
        } catch (Throwable t) {
            created.completeExceptionally(t);
            throw t;
        } finally {
            inFlightRequests.remove(cacheKey, created);
        }
    }
}
