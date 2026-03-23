package com.springalpha.backend.financial.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.springalpha.backend.financial.cache.MarketDataCacheService;
import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.BalanceSheet;
import com.springalpha.backend.financial.model.CashFlowStatement;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.model.IncomeStatement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class SecCompanyFactsFinancialDataService implements FinancialDataService {

    private static final Logger log = LoggerFactory.getLogger(SecCompanyFactsFinancialDataService.class);
    private static final String CACHE_SOURCE = "sec-v3-report-date";
    private static final Set<String> QUARTERLY_FORMS = Set.of("10-Q", "10-Q/A");
    private static final int QUARTERLY_MIN_DAYS = 75;
    private static final int QUARTERLY_MAX_DAYS = 110;
    private static final int ANNUAL_MIN_DAYS = 300;
    private static final int ANNUAL_MAX_DAYS = 380;
    private static final int REQUEST_TIMEOUT_SECONDS = 20;
    private static final int MAX_IN_MEMORY_BYTES = 16 * 1024 * 1024;
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private static final List<TagRef> REVENUE_TAGS = List.of(
            new TagRef("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            new TagRef("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
            new TagRef("us-gaap", "SalesRevenueNet"),
            new TagRef("us-gaap", "Revenues"),
            new TagRef("ifrs-full", "Revenue"));
    private static final List<TagRef> GROSS_PROFIT_TAGS = List.of(
            new TagRef("us-gaap", "GrossProfit"));
    private static final List<TagRef> COST_OF_REVENUE_TAGS = List.of(
            new TagRef("us-gaap", "CostOfRevenue"),
            new TagRef("us-gaap", "CostOfGoodsSold"),
            new TagRef("us-gaap", "CostOfGoodsAndServicesSold"),
            new TagRef("us-gaap", "CostOfSales"));
    private static final List<TagRef> COST_OF_SERVICES_TAGS = List.of(
            new TagRef("us-gaap", "CostOfServices"));
    private static final List<TagRef> OPERATING_INCOME_TAGS = List.of(
            new TagRef("us-gaap", "OperatingIncomeLoss"),
            new TagRef("ifrs-full", "ProfitLossFromOperatingActivities"));
    private static final List<TagRef> NET_INCOME_TAGS = List.of(
            new TagRef("us-gaap", "NetIncomeLoss"),
            new TagRef("ifrs-full", "ProfitLoss"));
    private static final List<TagRef> EPS_DILUTED_TAGS = List.of(
            new TagRef("us-gaap", "EarningsPerShareDiluted"),
            new TagRef("us-gaap", "IncomeLossFromContinuingOperationsPerDilutedShare"),
            new TagRef("ifrs-full", "DilutedEarningsLossPerShare"));
    private static final List<TagRef> ASSET_TAGS = List.of(
            new TagRef("us-gaap", "Assets"),
            new TagRef("ifrs-full", "Assets"));
    private static final List<TagRef> LIABILITY_TAGS = List.of(
            new TagRef("us-gaap", "Liabilities"),
            new TagRef("ifrs-full", "Liabilities"));
    private static final List<TagRef> EQUITY_TAGS = List.of(
            new TagRef("us-gaap", "StockholdersEquity"),
            new TagRef("us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
            new TagRef("us-gaap", "EntityCommonStockholdersEquity"),
            new TagRef("ifrs-full", "Equity"));
    private static final List<TagRef> SHORT_TERM_DEBT_TAGS = List.of(
            new TagRef("us-gaap", "LongTermDebtCurrent"),
            new TagRef("us-gaap", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
            new TagRef("us-gaap", "ShortTermBorrowings"));
    private static final List<TagRef> LONG_TERM_DEBT_TAGS = List.of(
            new TagRef("us-gaap", "LongTermDebtNoncurrent"),
            new TagRef("us-gaap", "LongTermDebtAndCapitalLeaseObligations"));
    private static final List<TagRef> OPERATING_CASH_FLOW_TAGS = List.of(
            new TagRef("us-gaap", "NetCashProvidedByUsedInOperatingActivities"),
            new TagRef("us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
            new TagRef("ifrs-full", "CashFlowsFromUsedInOperatingActivities"));
    private static final List<TagRef> CAPEX_TAGS = List.of(
            new TagRef("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment"),
            new TagRef("ifrs-full", "PurchaseOfPropertyPlantAndEquipment"));

    private final WebClient secDataClient;
    private final WebClient secFilesClient;
    private final FinancialCalculator calculator;
    private final MarketDataCacheService cacheService;
    private final Duration factsCacheTtl;
    private final Duration historyCacheTtl;
    private final Duration tickerMapTtl;
    private final ConcurrentHashMap<String, CompletableFuture<?>> inFlightRequests = new ConcurrentHashMap<>();

    private volatile CachedTickerDirectory tickerDirectory;

    @Autowired
    public SecCompanyFactsFinancialDataService(
            @Value("${app.sec.data-base-url:https://data.sec.gov}") String dataBaseUrl,
            @Value("${app.sec.www-base-url:https://www.sec.gov}") String filesBaseUrl,
            @Value("${app.sec.user-agent:SpringAlpha/1.0 (contact@springalpha.com)}") String userAgent,
            @Value("${app.sec.cache.facts-ttl:PT6H}") Duration factsCacheTtl,
            @Value("${app.sec.cache.history-ttl:PT24H}") Duration historyCacheTtl,
            @Value("${app.sec.cache.ticker-map-ttl:PT24H}") Duration tickerMapTtl,
            FinancialCalculator calculator,
            MarketDataCacheService cacheService) {
        this(buildWebClient(dataBaseUrl, userAgent), buildWebClient(filesBaseUrl, userAgent), calculator, cacheService,
                factsCacheTtl, historyCacheTtl, tickerMapTtl);
    }

    SecCompanyFactsFinancialDataService(
            WebClient secDataClient,
            WebClient secFilesClient,
            FinancialCalculator calculator,
            MarketDataCacheService cacheService,
            Duration factsCacheTtl,
            Duration historyCacheTtl,
            Duration tickerMapTtl) {
        this.secDataClient = secDataClient;
        this.secFilesClient = secFilesClient;
        this.calculator = calculator;
        this.cacheService = cacheService;
        this.factsCacheTtl = factsCacheTtl;
        this.historyCacheTtl = historyCacheTtl;
        this.tickerMapTtl = tickerMapTtl;
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
            log.info("💾 Returning cached SEC financial facts for {} ({})", upperTicker, normalizedReportType);
            return cachedFacts.get();
        }

        try {
            return executeDeduped(buildFactsCacheKey(upperTicker, normalizedReportType),
                    () -> loadFinancialFacts(upperTicker, normalizedReportType));
        } catch (Exception e) {
            log.warn("⚠️ Failed to fetch SEC company facts for {} ({}): {}", upperTicker, normalizedReportType,
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
            log.info("💾 Returning cached SEC historical data for {} ({})", upperTicker, normalizedReportType);
            return cachedHistory.get();
        }

        try {
            return executeDeduped(buildHistoryCacheKey(upperTicker, normalizedReportType),
                    () -> loadHistoricalData(upperTicker, normalizedReportType));
        } catch (Exception e) {
            log.warn("⚠️ Failed to fetch SEC historical data for {} ({}): {}", upperTicker, normalizedReportType,
                    e.getMessage());
            return Collections.emptyList();
        }
    }

    @Override
    public boolean isSupported(String ticker) {
        return resolveCik(ticker).isPresent();
    }

    @Override
    public String[] getSupportedTickers() {
        CachedTickerDirectory directory = currentTickerDirectory();
        if (directory == null || directory.entries().isEmpty()) {
            return new String[0];
        }
        return directory.entries().keySet().toArray(String[]::new);
    }

    @Override
    public Optional<String> resolveSecSearchIdentifier(String ticker) {
        if (ticker == null || ticker.isBlank()) {
            return Optional.empty();
        }
        return resolveCik(ticker.toUpperCase());
    }

    private FinancialFacts loadFinancialFacts(String upperTicker, String reportType) {
        Optional<String> cik = resolveCik(upperTicker);
        if (cik.isEmpty()) {
            return null;
        }

        JsonNode submissions = fetchJson(secDataClient, "/submissions/CIK" + cik.get() + ".json");
        JsonNode companyFacts = fetchJson(secDataClient, "/api/xbrl/companyfacts/CIK" + cik.get() + ".json");
        String companyName = firstNonBlank(
                submissions.path("name").asText(null),
                companyFacts.path("entityName").asText(null),
                upperTicker);

        List<FilingRef> filings = listCandidateFilings(submissions, reportType);
        if (filings.isEmpty()) {
            return null;
        }

        SnapshotSelection selection = findCurrentSnapshot(companyFacts, filings, companyName);
        if (selection == null) {
            return null;
        }

        FilingSnapshot previous = findPreviousSnapshot(
                companyFacts,
                filings.subList(selection.index() + 1, filings.size()),
                companyName,
                selection.snapshot());

        FinancialFacts facts = calculator.buildFinancialFacts(
                upperTicker,
                selection.snapshot().companyName(),
                selection.snapshot().periodLabel(),
                selection.snapshot().income(),
                selection.snapshot().balance(),
                selection.snapshot().cashFlow(),
                previous != null ? previous.income() : null,
                previous != null ? previous.cashFlow() : null);
        facts.setFilingDate(selection.snapshot().filing().filingDate());
        if ((facts.getCurrency() == null || facts.getCurrency().isBlank()) && selection.snapshot().currency() != null) {
            facts.setCurrency(selection.snapshot().currency());
        }

        if (cacheService != null && facts.getRevenue() != null) {
            cacheService.putFinancialFacts(CACHE_SOURCE, upperTicker, reportType, facts, factsCacheTtl);
        }
        return facts;
    }

    private List<HistoricalDataPoint> loadHistoricalData(String upperTicker, String reportType) {
        Optional<String> cik = resolveCik(upperTicker);
        if (cik.isEmpty()) {
            return Collections.emptyList();
        }

        JsonNode submissions = fetchJson(secDataClient, "/submissions/CIK" + cik.get() + ".json");
        JsonNode companyFacts = fetchJson(secDataClient, "/api/xbrl/companyfacts/CIK" + cik.get() + ".json");
        String companyName = firstNonBlank(
                submissions.path("name").asText(null),
                companyFacts.path("entityName").asText(null),
                upperTicker);

        List<FilingRef> filings = listCandidateFilings(submissions, reportType);
        if (filings.isEmpty()) {
            return Collections.emptyList();
        }

        Map<String, HistoricalDataPoint> deduped = new LinkedHashMap<>();
        for (FilingRef filing : filings) {
            FilingSnapshot snapshot = buildSnapshot(companyFacts, filing, companyName);
            if (snapshot == null || snapshot.income() == null) {
                continue;
            }

            HistoricalDataPoint point = HistoricalDataPoint.builder()
                    .period(snapshot.periodLabel())
                    .revenue(snapshot.income().getRevenue())
                    .netIncome(snapshot.income().getNetIncome())
                    .grossMargin(snapshot.income().getGrossMargin())
                    .operatingMargin(snapshot.income().getOperatingMargin())
                    .netMargin(snapshot.income().getNetMargin())
                    .build();
            deduped.putIfAbsent(point.getPeriod(), point);
            if (deduped.size() >= 5) {
                break;
            }
        }

        List<HistoricalDataPoint> history = new ArrayList<>(deduped.values());
        Collections.reverse(history);
        if (cacheService != null && !history.isEmpty()) {
            cacheService.putHistoricalData(CACHE_SOURCE, upperTicker, reportType, history, historyCacheTtl);
        }
        return history;
    }

    private SnapshotSelection findCurrentSnapshot(JsonNode companyFacts, List<FilingRef> filings, String companyName) {
        for (int idx = 0; idx < filings.size(); idx += 1) {
            FilingSnapshot snapshot = buildSnapshot(companyFacts, filings.get(idx), companyName);
            if (snapshot != null) {
                return new SnapshotSelection(idx, snapshot);
            }
        }
        return null;
    }

    private FilingSnapshot findPreviousSnapshot(
            JsonNode companyFacts,
            List<FilingRef> filings,
            String companyName,
            FilingSnapshot current) {
        for (FilingRef filing : filings) {
            FilingSnapshot candidate = buildSnapshot(companyFacts, filing, companyName);
            if (candidate == null || candidate.fiscalYear() == null) {
                continue;
            }

            if (isComparablePrevious(current, candidate)) {
                return candidate;
            }
        }
        return null;
    }

    private boolean isComparablePrevious(FilingSnapshot current, FilingSnapshot candidate) {
        if (current.fiscalYear() == null || candidate.fiscalYear() == null) {
            return false;
        }

        String currentPeriod = current.fiscalPeriod() == null ? "" : current.fiscalPeriod().toUpperCase();
        String candidatePeriod = candidate.fiscalPeriod() == null ? "" : candidate.fiscalPeriod().toUpperCase();

        if (currentPeriod.startsWith("Q")) {
            return current.fiscalYear() - 1 == candidate.fiscalYear()
                    && currentPeriod.equals(candidatePeriod);
        }

        return current.fiscalYear() - 1 == candidate.fiscalYear();
    }

    private FilingSnapshot buildSnapshot(JsonNode companyFacts, FilingRef filing, String companyName) {
        boolean quarterly = isQuarterlyForm(filing.form());

        FactValue revenue = selectFact(companyFacts, REVENUE_TAGS, filing, quarterly, true);
        FactValue grossProfit = selectFact(companyFacts, GROSS_PROFIT_TAGS, filing, quarterly, true);
        FactValue costOfRevenue = selectFact(companyFacts, COST_OF_REVENUE_TAGS, filing, quarterly, true);
        FactValue costOfServices = selectFact(companyFacts, COST_OF_SERVICES_TAGS, filing, quarterly, true);
        FactValue operatingIncome = selectFact(companyFacts, OPERATING_INCOME_TAGS, filing, quarterly, true);
        FactValue netIncome = selectFact(companyFacts, NET_INCOME_TAGS, filing, quarterly, true);
        FactValue dilutedEps = selectFact(companyFacts, EPS_DILUTED_TAGS, filing, quarterly, true);
        FactValue totalAssets = selectFact(companyFacts, ASSET_TAGS, filing, quarterly, false);
        FactValue totalLiabilities = selectFact(companyFacts, LIABILITY_TAGS, filing, quarterly, false);
        FactValue totalEquity = selectFact(companyFacts, EQUITY_TAGS, filing, quarterly, false);
        FactValue shortTermDebt = selectFact(companyFacts, SHORT_TERM_DEBT_TAGS, filing, quarterly, false);
        FactValue longTermDebt = selectFact(companyFacts, LONG_TERM_DEBT_TAGS, filing, quarterly, false);
        FactValue operatingCashFlow = selectFact(companyFacts, OPERATING_CASH_FLOW_TAGS, filing, quarterly, true);
        FactValue capex = selectFact(companyFacts, CAPEX_TAGS, filing, quarterly, true);

        FactValue canonical = firstNonNull(revenue, netIncome, totalAssets, operatingCashFlow, totalEquity);
        if (canonical == null) {
            return null;
        }

        FactValue effectiveCostOfRevenue = firstNonNull(costOfRevenue, costOfServices);
        FactValue effectiveGrossProfit = grossProfit != null
                ? grossProfit
                : deriveDifference(revenue, effectiveCostOfRevenue);

        IncomeStatement income = null;
        if (hasAnyValue(revenue, effectiveGrossProfit, operatingIncome, netIncome, dilutedEps, effectiveCostOfRevenue)) {
            income = IncomeStatement.builder()
                    .period(buildPeriodLabel(canonical.fiscalPeriod(), canonical.fiscalYear(), filing))
                    .reportedCurrency(resolveCurrency(revenue, netIncome, totalAssets))
                    .revenue(valueOrNull(revenue))
                    .costOfRevenue(valueOrNull(effectiveCostOfRevenue))
                    .grossProfit(valueOrNull(effectiveGrossProfit))
                    .operatingIncome(valueOrNull(operatingIncome))
                    .netIncome(valueOrNull(netIncome))
                    .earningsPerShareDiluted(valueOrNull(dilutedEps))
                    .build();
        }

        BalanceSheet balance = null;
        if (hasAnyValue(totalAssets, totalLiabilities, totalEquity, shortTermDebt, longTermDebt)) {
            balance = BalanceSheet.builder()
                    .period(buildPeriodLabel(canonical.fiscalPeriod(), canonical.fiscalYear(), filing))
                    .totalAssets(valueOrNull(totalAssets))
                    .totalLiabilities(valueOrNull(totalLiabilities))
                    .totalEquity(valueOrNull(totalEquity))
                    .shortTermDebt(valueOrNull(shortTermDebt))
                    .longTermDebt(valueOrNull(longTermDebt))
                    .build();
        }

        CashFlowStatement cashFlow = null;
        if (hasAnyValue(operatingCashFlow, capex)) {
            cashFlow = CashFlowStatement.builder()
                    .period(buildPeriodLabel(canonical.fiscalPeriod(), canonical.fiscalYear(), filing))
                    .netIncome(valueOrNull(netIncome))
                    .operatingCashFlow(valueOrNull(operatingCashFlow))
                    .capitalExpenditures(valueOrNull(capex))
                    .build();
        }

        return new FilingSnapshot(
                filing,
                buildPeriodLabel(canonical.fiscalPeriod(), canonical.fiscalYear(), filing),
                canonical.fiscalYear(),
                canonical.fiscalPeriod(),
                income,
                balance,
                cashFlow,
                firstNonBlank(companyName, filing.ticker()),
                resolveCurrency(revenue, netIncome, totalAssets));
    }

    private FactValue selectFact(
            JsonNode companyFacts,
            List<TagRef> tagRefs,
            FilingRef filing,
            boolean quarterly,
            boolean durationBased) {
        for (TagRef tagRef : tagRefs) {
            FactValue value = selectFact(companyFacts, tagRef, filing, quarterly, durationBased);
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private FactValue selectFact(
            JsonNode companyFacts,
            TagRef tagRef,
            FilingRef filing,
            boolean quarterly,
            boolean durationBased) {
        JsonNode units = companyFacts.path("facts")
                .path(tagRef.namespace())
                .path(tagRef.tag())
                .path("units");
        if (units.isMissingNode() || !units.isObject()) {
            return null;
        }

        List<FactValue> candidates = new ArrayList<>();
        units.fields().forEachRemaining(entry -> {
            JsonNode values = entry.getValue();
            if (!values.isArray()) {
                return;
            }

            for (JsonNode valueNode : values) {
                FactValue value = toFactValue(valueNode, entry.getKey());
                if (value == null || !filing.normalizedAccessionNumber().equals(value.normalizedAccessionNumber())) {
                    continue;
                }
                if (value.segmented()) {
                    continue;
                }
                if (durationBased && !matchesExpectedDuration(value, quarterly)) {
                    continue;
                }
                candidates.add(value);
            }
        });

        if (candidates.isEmpty()) {
            return null;
        }

        candidates.sort(Comparator
                .comparingLong((FactValue value) -> reportDateDistance(value, filing))
                .thenComparing(FactValue::segmented)
                .thenComparing(value -> value.frame() == null ? 0 : 1)
                .thenComparing(value -> durationDistance(value, quarterly))
                .thenComparing(FactValue::filingDate, Comparator.nullsLast(Comparator.reverseOrder())));
        return candidates.get(0);
    }

    private long reportDateDistance(FactValue value, FilingRef filing) {
        LocalDate reportDate = parseDate(firstNonBlank(filing.reportDate(), filing.filingDate()));
        LocalDate factEndDate = parseDate(value.endDate());
        if (reportDate == null || factEndDate == null) {
            return Long.MAX_VALUE;
        }
        return Math.abs(ChronoUnit.DAYS.between(reportDate, factEndDate));
    }

    private boolean matchesExpectedDuration(FactValue value, boolean quarterly) {
        if (!value.durationBased()) {
            return false;
        }

        long durationDays = value.durationDays();
        if (quarterly) {
            return durationDays >= QUARTERLY_MIN_DAYS && durationDays <= QUARTERLY_MAX_DAYS;
        }
        return durationDays >= ANNUAL_MIN_DAYS && durationDays <= ANNUAL_MAX_DAYS;
    }

    private long durationDistance(FactValue value, boolean quarterly) {
        long target = quarterly ? 91L : 365L;
        return Math.abs(value.durationDays() - target);
    }

    private FactValue toFactValue(JsonNode valueNode, String unit) {
        BigDecimal value = toBigDecimal(valueNode.path("val"));
        if (value == null) {
            return null;
        }

        String accessionNumber = valueNode.path("accn").asText(null);
        String fiscalPeriod = valueNode.path("fp").asText(null);
        Integer fiscalYear = valueNode.path("fy").canConvertToInt() ? valueNode.path("fy").intValue() : null;
        String start = valueNode.path("start").asText(null);
        String end = valueNode.path("end").asText(null);
        String filingDate = valueNode.path("filed").asText(null);
        String frame = valueNode.path("frame").asText(null);
        boolean segmented = valueNode.has("segment") && !valueNode.path("segment").isMissingNode();

        long durationDays = 0L;
        boolean durationBased = start != null && !start.isBlank() && end != null && !end.isBlank();
        if (durationBased) {
            try {
                durationDays = ChronoUnit.DAYS.between(LocalDate.parse(start), LocalDate.parse(end));
            } catch (DateTimeParseException e) {
                durationDays = 0L;
            }
        }

        return new FactValue(
                value,
                unit,
                fiscalPeriod,
                fiscalYear,
                accessionNumber,
                normalizeAccession(accessionNumber),
                filingDate,
                start,
                end,
                frame,
                segmented,
                durationBased,
                durationDays);
    }

    private LocalDate parseDate(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(value);
        } catch (DateTimeParseException e) {
            return null;
        }
    }

    private List<FilingRef> listCandidateFilings(JsonNode submissions, String reportType) {
        JsonNode recent = submissions.path("filings").path("recent");
        if (recent.isMissingNode()) {
            return List.of();
        }

        return filterFilings(recent, QUARTERLY_FORMS, submissions.path("ticker").asText(null));
    }

    private List<FilingRef> filterFilings(JsonNode recent, Set<String> acceptedForms, String ticker) {
        List<FilingRef> filings = new ArrayList<>();
        JsonNode forms = recent.path("form");
        for (int idx = 0; idx < forms.size(); idx += 1) {
            String form = forms.path(idx).asText("");
            if (!acceptedForms.contains(form)) {
                continue;
            }

            String accessionNumber = recent.path("accessionNumber").path(idx).asText(null);
            if (accessionNumber == null || accessionNumber.isBlank()) {
                continue;
            }

            filings.add(new FilingRef(
                    form,
                    recent.path("filingDate").path(idx).asText(null),
                    recent.path("reportDate").path(idx).asText(null),
                    accessionNumber,
                    normalizeAccession(accessionNumber),
                    ticker));
        }
        return filings;
    }

    private Optional<String> resolveCik(String ticker) {
        if (ticker == null || ticker.isBlank()) {
            return Optional.empty();
        }

        CachedTickerDirectory cached = currentTickerDirectory();
        for (String candidate : tickerLookupCandidates(ticker)) {
            String cik = cached.entries().get(candidate);
            if (cik != null) {
                return Optional.of(cik);
            }
        }
        return Optional.empty();
    }

    private List<String> tickerLookupCandidates(String ticker) {
        String upper = ticker.toUpperCase().trim();
        if (upper.isBlank()) {
            return List.of();
        }

        List<String> candidates = new ArrayList<>();
        candidates.add(upper);

        String dotToDash = upper.replace('.', '-');
        if (!dotToDash.equals(upper)) {
            candidates.add(dotToDash);
        }

        String dashToDot = upper.replace('-', '.');
        if (!dashToDot.equals(upper)) {
            candidates.add(dashToDot);
        }

        return candidates;
    }

    private CachedTickerDirectory currentTickerDirectory() {
        CachedTickerDirectory cached = tickerDirectory;
        Instant now = Instant.now();
        if (cached == null || cached.expiresAt().isBefore(now)) {
            synchronized (this) {
                cached = tickerDirectory;
                if (cached == null || cached.expiresAt().isBefore(now)) {
                    tickerDirectory = loadTickerDirectory(now.plus(tickerMapTtl));
                    cached = tickerDirectory;
                }
            }
        }
        return cached;
    }

    private CachedTickerDirectory loadTickerDirectory(Instant expiresAt) {
        JsonNode directoryJson = fetchJson(secFilesClient, "/files/company_tickers.json");
        Map<String, String> entries = new HashMap<>();
        directoryJson.fields().forEachRemaining(entry -> {
            JsonNode company = entry.getValue();
            String ticker = company.path("ticker").asText(null);
            JsonNode cikNode = company.path("cik_str");
            if (ticker == null || ticker.isBlank() || cikNode.isMissingNode()) {
                return;
            }
            entries.put(ticker.toUpperCase(), padCik(cikNode.asText()));
        });
        return new CachedTickerDirectory(entries, expiresAt);
    }

    private JsonNode fetchJson(WebClient client, String uri) {
        String body = client.get()
                .uri(uri)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(REQUEST_TIMEOUT_SECONDS))
                .block();

        if (body == null || body.isBlank()) {
            throw new IllegalStateException("Empty SEC JSON response for " + uri);
        }

        try {
            return OBJECT_MAPPER.readTree(body);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to parse SEC JSON for " + uri + ": " + e.getMessage(), e);
        }
    }

    private static WebClient buildWebClient(String baseUrl, String userAgent) {
        reactor.netty.http.client.HttpClient httpClient = reactor.netty.http.client.HttpClient.create()
                .compress(true)
                .option(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS, 10000)
                .responseTimeout(Duration.ofSeconds(REQUEST_TIMEOUT_SECONDS))
                .followRedirect(true)
                .doOnConnected(conn -> conn.addHandlerLast(new io.netty.handler.timeout.ReadTimeoutHandler(REQUEST_TIMEOUT_SECONDS))
                        .addHandlerLast(new io.netty.handler.timeout.WriteTimeoutHandler(REQUEST_TIMEOUT_SECONDS)));

        ExchangeStrategies strategies = ExchangeStrategies.builder()
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(MAX_IN_MEMORY_BYTES))
                .build();

        return WebClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader("User-Agent", userAgent)
                .exchangeStrategies(strategies)
                .clientConnector(new org.springframework.http.client.reactive.ReactorClientHttpConnector(httpClient))
                .build();
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

    private boolean isQuarterlyForm(String form) {
        return QUARTERLY_FORMS.contains(form);
    }

    private String buildFactsCacheKey(String ticker, String reportType) {
        return CACHE_SOURCE + ":facts:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String buildHistoryCacheKey(String ticker, String reportType) {
        return CACHE_SOURCE + ":history:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private String buildPeriodLabel(String fiscalPeriod, Integer fiscalYear, FilingRef filing) {
        String year = fiscalYear != null
                ? Integer.toString(fiscalYear)
                : extractYear(firstNonBlank(filing.reportDate(), filing.filingDate()));
        String normalizedPeriod = fiscalPeriod == null ? "" : fiscalPeriod.trim().toUpperCase();

        if (!normalizedPeriod.isBlank()) {
            if (normalizedPeriod.startsWith("Q")) {
                return year.isBlank() ? normalizedPeriod : "FY" + year + " " + normalizedPeriod;
            }
            return year.isBlank() ? normalizedPeriod : normalizedPeriod + " " + year;
        }

        if (isQuarterlyForm(filing.form())) {
            return year.isBlank() ? "Q" : "Q " + year;
        }
        return year.isBlank() ? "FY" : "FY " + year;
    }

    private String resolveCurrency(FactValue... candidates) {
        for (FactValue candidate : candidates) {
            if (candidate == null || candidate.unit() == null || candidate.unit().isBlank()) {
                continue;
            }
            String unit = candidate.unit();
            int slash = unit.indexOf('/');
            return slash >= 0 ? unit.substring(0, slash) : unit;
        }
        return null;
    }

    private boolean hasAnyValue(FactValue... values) {
        for (FactValue value : values) {
            if (value != null && value.value() != null) {
                return true;
            }
        }
        return false;
    }

    private FactValue firstNonNull(FactValue... values) {
        for (FactValue value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private BigDecimal valueOrNull(FactValue value) {
        return value == null ? null : value.value();
    }

    private FactValue deriveDifference(FactValue minuend, FactValue subtrahend) {
        if (minuend == null || subtrahend == null || minuend.value() == null || subtrahend.value() == null) {
            return null;
        }

        return new FactValue(
                minuend.value().subtract(subtrahend.value()),
                minuend.unit(),
                firstNonBlank(minuend.fiscalPeriod(), subtrahend.fiscalPeriod()),
                minuend.fiscalYear() != null ? minuend.fiscalYear() : subtrahend.fiscalYear(),
                minuend.accessionNumber(),
                minuend.normalizedAccessionNumber(),
                firstNonBlank(minuend.filingDate(), subtrahend.filingDate()),
                firstNonBlank(minuend.startDate(), subtrahend.startDate()),
                firstNonBlank(minuend.endDate(), subtrahend.endDate()),
                minuend.frame(),
                false,
                minuend.durationBased(),
                minuend.durationDays());
    }

    private BigDecimal toBigDecimal(JsonNode node) {
        if (node == null || node.isMissingNode() || node.isNull()) {
            return null;
        }
        try {
            return new BigDecimal(node.asText());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return "";
    }

    private String extractYear(String dateValue) {
        if (dateValue == null || dateValue.isBlank()) {
            return "";
        }
        String trimmed = dateValue.trim();
        return trimmed.length() >= 4 ? trimmed.substring(0, 4) : "";
    }

    private String padCik(String cik) {
        String digits = cik == null ? "" : cik.replaceAll("\\D", "");
        return String.format("%010d", Long.parseLong(digits));
    }

    private String normalizeAccession(String accessionNumber) {
        return accessionNumber == null ? "" : accessionNumber.replace("-", "").trim();
    }

    record TagRef(String namespace, String tag) {
    }

    record FilingRef(
            String form,
            String filingDate,
            String reportDate,
            String accessionNumber,
            String normalizedAccessionNumber,
            String ticker) {
    }

    record FactValue(
            BigDecimal value,
            String unit,
            String fiscalPeriod,
            Integer fiscalYear,
            String accessionNumber,
            String normalizedAccessionNumber,
            String filingDate,
            String startDate,
            String endDate,
            String frame,
            boolean segmented,
            boolean durationBased,
            long durationDays) {
    }

    record FilingSnapshot(
            FilingRef filing,
            String periodLabel,
            Integer fiscalYear,
            String fiscalPeriod,
            IncomeStatement income,
            BalanceSheet balance,
            CashFlowStatement cashFlow,
            String companyName,
            String currency) {
    }

    record SnapshotSelection(int index, FilingSnapshot snapshot) {
    }

    record CachedTickerDirectory(Map<String, String> entries, Instant expiresAt) {
    }
}
