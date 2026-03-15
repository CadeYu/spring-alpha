package com.springalpha.backend.service.signals;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class BusinessSignalSnapshotService {

    static final String EXTRACTOR_VERSION = "v3";
    private static final Logger log = LoggerFactory.getLogger(BusinessSignalSnapshotService.class);

    private final BusinessSignalSnapshotRepository repository;
    private final BusinessSignalExtractor extractor;
    private final ObjectMapper objectMapper;

    public BusinessSignalSnapshotService(
            BusinessSignalSnapshotRepository repository,
            BusinessSignalExtractor extractor,
            ObjectMapper objectMapper) {
        this.repository = repository;
        this.extractor = extractor;
        this.objectMapper = objectMapper;
    }

    public BusinessSignals getOrExtract(
            String ticker,
            String reportType,
            FinancialFacts facts,
            Map<String, String> textEvidence,
            boolean evidenceAvailable) {
        String normalizedReportType = normalizeReportType(reportType);
        String periodLabel = facts != null && facts.getPeriod() != null ? facts.getPeriod() : "unknown-period";
        String filingDate = facts != null ? facts.getFilingDate() : null;
        String snapshotKey = buildSnapshotKey(ticker, normalizedReportType, periodLabel, filingDate, EXTRACTOR_VERSION);
        String sourceHash = buildSourceHash(ticker, normalizedReportType, facts, textEvidence, evidenceAvailable);

        Optional<BusinessSignals> cached = repository.findById(snapshotKey)
                .filter(entry -> EXTRACTOR_VERSION.equals(entry.getExtractorVersion()))
                .filter(entry -> sourceHash.equals(entry.getSourceHash()))
                .flatMap(this::deserialize);

        if (cached.isPresent()) {
            log.info("💾 Returning cached business signals for {} ({})", ticker, normalizedReportType);
            return cached.get();
        }

        BusinessSignals extracted = extractor.extract(ticker, normalizedReportType, facts, textEvidence);
        write(snapshotKey, ticker, normalizedReportType, periodLabel, filingDate, sourceHash, extracted);
        return extracted;
    }

    private Optional<BusinessSignals> deserialize(BusinessSignalSnapshotEntry entry) {
        try {
            BusinessSignals signals = objectMapper.readValue(entry.getSignalsJson(), BusinessSignals.class);
            if (containsMachineReadableArtifacts(signals)) {
                log.warn("⚠️ Invalidating business-signal snapshot {} because it still contains machine-readable XBRL artifacts",
                        entry.getSnapshotKey());
                repository.deleteById(entry.getSnapshotKey());
                return Optional.empty();
            }
            return Optional.of(signals);
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to deserialize business-signal snapshot {}: {}", entry.getSnapshotKey(), e.getMessage());
            repository.deleteById(entry.getSnapshotKey());
            return Optional.empty();
        }
    }

    private void write(String snapshotKey, String ticker, String reportType, String periodLabel, String filingDate,
            String sourceHash, BusinessSignals signals) {
        try {
            Instant now = Instant.now();
            repository.save(BusinessSignalSnapshotEntry.builder()
                    .snapshotKey(snapshotKey)
                    .ticker(ticker.toUpperCase())
                    .reportType(reportType)
                    .periodLabel(periodLabel)
                    .filingDate(filingDate)
                    .sourceHash(sourceHash)
                    .extractorVersion(EXTRACTOR_VERSION)
                    .signalsJson(objectMapper.writeValueAsString(signals))
                    .createdAt(now)
                    .updatedAt(now)
                    .build());
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to serialize business-signal snapshot {}: {}", snapshotKey, e.getMessage());
        }
    }

    private boolean containsMachineReadableArtifacts(BusinessSignals signals) {
        if (signals == null) {
            return false;
        }

        return collectSignalText(signals).stream()
                .filter(value -> value != null && !value.isBlank())
                .anyMatch(extractor::containsMachineReadableArtifact);
    }

    private List<String> collectSignalText(BusinessSignals signals) {
        List<String> values = new ArrayList<>();
        addSignalText(values, signals.getSegmentPerformance());
        addSignalText(values, signals.getProductServiceUpdates());
        addSignalText(values, signals.getManagementFocus());
        addSignalText(values, signals.getStrategicMoves());
        addSignalText(values, signals.getCapexSignals());
        addSignalText(values, signals.getRiskSignals());
        if (signals.getEvidenceRefs() != null) {
            signals.getEvidenceRefs().forEach(ref -> {
                values.add(ref.getTopic());
                values.add(ref.getSection());
                values.add(ref.getExcerpt());
            });
        }
        return values;
    }

    private void addSignalText(List<String> values, List<BusinessSignals.SignalItem> items) {
        if (items == null) {
            return;
        }
        items.forEach(item -> {
            values.add(item.getTitle());
            values.add(item.getSummary());
            values.add(item.getEvidenceSection());
            values.add(item.getEvidenceSnippet());
        });
    }

    private String buildSnapshotKey(String ticker, String reportType, String periodLabel, String filingDate,
            String extractorVersion) {
        String safeDate = filingDate == null || filingDate.isBlank() ? "unknown-date" : filingDate;
        return "signals:" + ticker.toUpperCase() + ":" + reportType + ":" + safeDate + ":"
                + sanitize(periodLabel) + ":" + sanitize(extractorVersion);
    }

    private String buildSourceHash(String ticker, String reportType, FinancialFacts facts, Map<String, String> textEvidence,
            boolean evidenceAvailable) {
        Map<String, Object> fingerprint = new LinkedHashMap<>();
        fingerprint.put("ticker", ticker.toUpperCase());
        fingerprint.put("reportType", reportType);
        fingerprint.put("period", facts != null ? facts.getPeriod() : null);
        fingerprint.put("filingDate", facts != null ? facts.getFilingDate() : null);
        fingerprint.put("revenue", facts != null ? facts.getRevenue() : null);
        fingerprint.put("revenueYoY", facts != null ? facts.getRevenueYoY() : null);
        fingerprint.put("grossMargin", facts != null ? facts.getGrossMargin() : null);
        fingerprint.put("netMargin", facts != null ? facts.getNetMargin() : null);
        fingerprint.put("evidenceAvailable", evidenceAvailable);
        fingerprint.put("textEvidence", textEvidence);

        try {
            return sha256(objectMapper.writeValueAsString(fingerprint));
        } catch (JsonProcessingException e) {
            return sha256(String.valueOf(fingerprint));
        }
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is unavailable", e);
        }
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private String sanitize(String value) {
        return value == null ? "unknown-period" : value.replaceAll("[^A-Za-z0-9_-]+", "-");
    }
}
