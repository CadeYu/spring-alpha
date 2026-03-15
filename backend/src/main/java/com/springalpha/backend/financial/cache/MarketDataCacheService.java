package com.springalpha.backend.financial.cache;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Service
public class MarketDataCacheService {

    private static final Logger log = LoggerFactory.getLogger(MarketDataCacheService.class);
    private static final String DEFAULT_SOURCE = "fmp";

    private final MarketDataCacheRepository repository;
    private final ObjectMapper objectMapper;

    public MarketDataCacheService(MarketDataCacheRepository repository, ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    public Optional<FinancialFacts> getFinancialFacts(String ticker, boolean includeExpired) {
        return getFinancialFacts(DEFAULT_SOURCE, ticker, "quarterly", includeExpired);
    }

    public Optional<FinancialFacts> getFinancialFacts(String ticker, String reportType, boolean includeExpired) {
        return getFinancialFacts(DEFAULT_SOURCE, ticker, reportType, includeExpired);
    }

    public Optional<FinancialFacts> getFinancialFacts(
            String source,
            String ticker,
            String reportType,
            boolean includeExpired) {
        return read(buildFactsCacheKey(source, ticker, reportType), FinancialFacts.class, includeExpired);
    }

    public void putFinancialFacts(String ticker, FinancialFacts facts, Duration ttl) {
        putFinancialFacts(DEFAULT_SOURCE, ticker, "quarterly", facts, ttl);
    }

    public void putFinancialFacts(String ticker, String reportType, FinancialFacts facts, Duration ttl) {
        putFinancialFacts(DEFAULT_SOURCE, ticker, reportType, facts, ttl);
    }

    public void putFinancialFacts(String source, String ticker, String reportType, FinancialFacts facts, Duration ttl) {
        write(buildFactsCacheKey(source, ticker, reportType), source, facts, ttl);
    }

    public Optional<List<HistoricalDataPoint>> getHistoricalData(String ticker, boolean includeExpired) {
        return getHistoricalData(DEFAULT_SOURCE, ticker, "quarterly", includeExpired);
    }

    public Optional<List<HistoricalDataPoint>> getHistoricalData(String ticker, String reportType, boolean includeExpired) {
        return getHistoricalData(DEFAULT_SOURCE, ticker, reportType, includeExpired);
    }

    public Optional<List<HistoricalDataPoint>> getHistoricalData(
            String source,
            String ticker,
            String reportType,
            boolean includeExpired) {
        JavaType type = objectMapper.getTypeFactory()
                .constructCollectionType(List.class, HistoricalDataPoint.class);
        return read(buildHistoryCacheKey(source, ticker, reportType), type, includeExpired);
    }

    public void putHistoricalData(String ticker, List<HistoricalDataPoint> historyData, Duration ttl) {
        putHistoricalData(DEFAULT_SOURCE, ticker, "quarterly", historyData, ttl);
    }

    public void putHistoricalData(String ticker, String reportType, List<HistoricalDataPoint> historyData, Duration ttl) {
        putHistoricalData(DEFAULT_SOURCE, ticker, reportType, historyData, ttl);
    }

    public void putHistoricalData(
            String source,
            String ticker,
            String reportType,
            List<HistoricalDataPoint> historyData,
            Duration ttl) {
        write(buildHistoryCacheKey(source, ticker, reportType), source, historyData, ttl);
    }

    private <T> Optional<T> read(String cacheKey, Class<T> targetType, boolean includeExpired) {
        return repository.findById(cacheKey)
                .filter(entry -> includeExpired || !isExpired(entry))
                .flatMap(entry -> deserialize(cacheKey, entry.getPayloadJson(), objectMapper.constructType(targetType)));
    }

    private <T> Optional<T> read(String cacheKey, JavaType targetType, boolean includeExpired) {
        return repository.findById(cacheKey)
                .filter(entry -> includeExpired || !isExpired(entry))
                .flatMap(entry -> deserialize(cacheKey, entry.getPayloadJson(), targetType));
    }

    private <T> Optional<T> deserialize(String cacheKey, String payloadJson, JavaType targetType) {
        try {
            return Optional.of(objectMapper.readValue(payloadJson, targetType));
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to deserialize market-data cache entry {}: {}", cacheKey, e.getMessage());
            repository.deleteById(cacheKey);
            return Optional.empty();
        }
    }

    private void write(String cacheKey, String source, Object payload, Duration ttl) {
        try {
            Instant now = Instant.now();
            repository.save(MarketDataCacheEntry.builder()
                    .cacheKey(cacheKey)
                    .payloadJson(objectMapper.writeValueAsString(payload))
                    .source(source)
                    .updatedAt(now)
                    .expiresAt(now.plus(ttl))
                    .build());
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to serialize market-data cache entry {}: {}", cacheKey, e.getMessage());
        }
    }

    private boolean isExpired(MarketDataCacheEntry entry) {
        return entry.getExpiresAt() != null && entry.getExpiresAt().isBefore(Instant.now());
    }

    private String buildFactsCacheKey(String source, String ticker, String reportType) {
        return source.toLowerCase() + ":facts:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String buildHistoryCacheKey(String source, String ticker, String reportType) {
        return source.toLowerCase() + ":history:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }
}
