package com.springalpha.backend.financial.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class YahooFinanceMarketDataService implements MarketEnrichmentService {

    private static final String PROVIDER = "yfinance";
    private static final Duration DEFAULT_TIMEOUT = Duration.ofSeconds(20);

    private final ObjectMapper objectMapper;
    private final String pythonExecutable;
    private final Duration cacheTtl;
    private final Duration executionTimeout;
    private final ProcessRunner processRunner;
    private final ConcurrentHashMap<String, CachedEntry> cache = new ConcurrentHashMap<>();

    private volatile Path helperScriptPath;

    @Autowired
    public YahooFinanceMarketDataService(
            ObjectMapper objectMapper,
            @Value("${app.yfinance.python-executable:python3}") String pythonExecutable,
            @Value("${app.yfinance.cache-ttl:PT6H}") Duration cacheTtl,
            @Value("${app.yfinance.execution-timeout:PT20S}") Duration executionTimeout) {
        this(objectMapper, pythonExecutable, cacheTtl, executionTimeout, new DefaultProcessRunner());
    }

    YahooFinanceMarketDataService(
            ObjectMapper objectMapper,
            String pythonExecutable,
            Duration cacheTtl,
            Duration executionTimeout,
            ProcessRunner processRunner) {
        this.objectMapper = objectMapper;
        this.pythonExecutable = pythonExecutable;
        this.cacheTtl = cacheTtl;
        this.executionTimeout = executionTimeout;
        this.processRunner = processRunner;
    }

    @Override
    public MarketSupplementalData getSupplementalData(String ticker, String reportType) {
        String upperTicker = ticker == null ? null : ticker.toUpperCase();
        if (upperTicker == null || upperTicker.isBlank()) {
            return unavailable("Ticker was empty.");
        }

        String cacheKey = upperTicker + ":" + normalizeReportType(reportType);
        CachedEntry cached = cache.get(cacheKey);
        if (cached != null && cached.expiresAt().isAfter(Instant.now())) {
            return cached.data();
        }

        try {
            Path helper = ensureHelperScript();
            String lastError = null;
            MarketSupplementalData fallbackData = null;
            for (String tickerCandidate : resolveTickerCandidates(upperTicker)) {
                for (String candidate : resolvePythonCandidates()) {
                    ProcessResult result = processRunner.run(List.of(
                            candidate,
                            helper.toString(),
                            tickerCandidate), executionTimeout);

                    if (result.exitCode() != 0) {
                        lastError = normalizeError(result.stderr(), result.stdout());
                        continue;
                    }

                    YahooHelperPayload payload = objectMapper.readValue(result.stdout(), YahooHelperPayload.class);
                    MarketSupplementalData data = new MarketSupplementalData(
                            PROVIDER,
                            payload.profileAvailable(),
                            payload.quoteAvailable(),
                            payload.valuationAvailable(),
                            payload.companyName(),
                            payload.sector(),
                            payload.industry(),
                            payload.securityType(),
                            payload.latestPrice(),
                            payload.marketCap(),
                            payload.priceToEarningsRatio(),
                            payload.priceToBookRatio(),
                            payload.quarterlyFinancials() == null ? List.of() : payload.quarterlyFinancials(),
                            payload.message(),
                            payload.businessSummary());
                    log.info("📊 Yahoo enrichment for {} via {} ({}) returned quarterlySnapshots={}",
                            upperTicker,
                            tickerCandidate,
                            normalizeReportType(reportType),
                            data.quarterlyFinancials() == null ? 0 : data.quarterlyFinancials().size());

                    if (hasUsefulMarketData(data)) {
                        cache.put(cacheKey, new CachedEntry(data, Instant.now().plus(cacheTtl)));
                        return data;
                    }

                    if (fallbackData == null) {
                        fallbackData = data;
                    }
                }
            }

            if (fallbackData != null) {
                return fallbackData;
            }

            return unavailable(lastError);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("⚠️ Yahoo Finance enrichment interrupted for {}: {}", upperTicker, e.getMessage());
            return unavailable("Yahoo Finance helper interrupted.");
        } catch (Exception e) {
            log.warn("⚠️ Yahoo Finance enrichment failed for {}: {}", upperTicker, e.getMessage());
            return unavailable(e.getMessage());
        }
    }

    private MarketSupplementalData unavailable(String message) {
        return new MarketSupplementalData(
                PROVIDER,
                false,
                false,
                false,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                Collections.emptyList(),
                message == null || message.isBlank()
                        ? "Yahoo Finance enrichment unavailable."
                        : "Yahoo Finance enrichment unavailable: " + message,
                null);
    }

    private String normalizeError(String stderr, String stdout) {
        if (stderr != null && !stderr.isBlank()) {
            return stderr.trim();
        }
        if (stdout != null && !stdout.isBlank()) {
            return stdout.trim();
        }
        return "Unknown helper error";
    }

    private Path ensureHelperScript() throws IOException {
        Path existing = helperScriptPath;
        if (existing != null && Files.exists(existing)) {
            return existing;
        }

        synchronized (this) {
            if (helperScriptPath != null && Files.exists(helperScriptPath)) {
                return helperScriptPath;
            }

            ClassPathResource resource = new ClassPathResource("python/yfinance_market_data.py");
            Path temp = Files.createTempFile("spring-alpha-yfinance-", ".py");
            temp.toFile().deleteOnExit();
            try (InputStream in = resource.getInputStream()) {
                Files.writeString(temp, new String(in.readAllBytes(), StandardCharsets.UTF_8), StandardCharsets.UTF_8);
            }
            helperScriptPath = temp;
            return temp;
        }
    }

    private List<String> resolvePythonCandidates() {
        LinkedHashSet<String> candidates = new LinkedHashSet<>();
        if (pythonExecutable != null && !pythonExecutable.isBlank()) {
            candidates.add(pythonExecutable);
        }

        Path cwd = Path.of("").toAbsolutePath().normalize();
        addIfExists(candidates, cwd.resolve(".venv/bin/python"));
        addIfExists(candidates, cwd.resolve("../.venv/bin/python").normalize());
        addIfExists(candidates, cwd.resolve("backend/.venv/bin/python").normalize());

        if (candidates.isEmpty()) {
            candidates.add("python3");
        }
        return List.copyOf(candidates);
    }

    private void addIfExists(LinkedHashSet<String> candidates, Path path) {
        if (path != null && Files.exists(path)) {
            candidates.add(path.toString());
        }
    }

    private List<String> resolveTickerCandidates(String ticker) {
        LinkedHashSet<String> candidates = new LinkedHashSet<>();
        candidates.add(ticker);

        if (ticker.contains(".")) {
            candidates.add(ticker.replace('.', '-'));
        }
        if (ticker.contains("-")) {
            candidates.add(ticker.replace('-', '.'));
        }

        return List.copyOf(candidates);
    }

    private boolean hasUsefulMarketData(MarketSupplementalData data) {
        return data.profileAvailable()
                || data.quoteAvailable()
                || data.valuationAvailable()
                || (data.quarterlyFinancials() != null && !data.quarterlyFinancials().isEmpty());
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private record CachedEntry(MarketSupplementalData data, Instant expiresAt) {
    }

    private record YahooHelperPayload(
            boolean profileAvailable,
            boolean quoteAvailable,
            boolean valuationAvailable,
            String companyName,
            String sector,
            String industry,
            String securityType,
            BigDecimal latestPrice,
            BigDecimal marketCap,
            BigDecimal priceToEarningsRatio,
            BigDecimal priceToBookRatio,
            List<MarketSupplementalData.QuarterlyFinancialSnapshot> quarterlyFinancials,
            String message,
            String businessSummary) {
    }

    interface ProcessRunner {
        ProcessResult run(List<String> command, Duration timeout) throws IOException, InterruptedException;
    }

    record ProcessResult(int exitCode, String stdout, String stderr) {
    }

    private static class DefaultProcessRunner implements ProcessRunner {

        @Override
        public ProcessResult run(List<String> command, Duration timeout) throws IOException, InterruptedException {
            Process process = new ProcessBuilder(command).start();
            boolean finished = process.waitFor(timeout == null ? DEFAULT_TIMEOUT.toSeconds() : timeout.toSeconds(),
                    TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new IOException("Timed out waiting for Yahoo Finance helper process");
            }

            String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            String stderr = new String(process.getErrorStream().readAllBytes(), StandardCharsets.UTF_8);
            return new ProcessResult(process.exitValue(), stdout, stderr);
        }
    }
}
