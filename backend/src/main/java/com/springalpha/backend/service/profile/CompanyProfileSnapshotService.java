package com.springalpha.backend.service.profile;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

@Service
public class CompanyProfileSnapshotService {

    static final String EXTRACTOR_VERSION = "v5";
    private static final Logger log = LoggerFactory.getLogger(CompanyProfileSnapshotService.class);

    private final CompanyProfileSnapshotRepository repository;
    private final CompanyProfileExtractor extractor;
    private final ObjectMapper objectMapper;

    public CompanyProfileSnapshotService(
            CompanyProfileSnapshotRepository repository,
            CompanyProfileExtractor extractor,
            ObjectMapper objectMapper) {
        this.repository = repository;
        this.extractor = extractor;
        this.objectMapper = objectMapper;
    }

    public CompanyProfile getOrExtract(
            String ticker,
            String reportType,
            FinancialFacts facts,
            BusinessSignals businessSignals,
            Map<String, String> textEvidence) {
        String normalizedReportType = "quarterly";
        String periodLabel = facts != null && facts.getPeriod() != null ? facts.getPeriod() : "unknown-period";
        String filingDate = facts != null ? facts.getFilingDate() : null;
        String snapshotKey = buildSnapshotKey(ticker, normalizedReportType, periodLabel, filingDate, EXTRACTOR_VERSION);
        String sourceHash = buildSourceHash(ticker, normalizedReportType, facts, businessSignals, textEvidence);

        Optional<CompanyProfile> cached = repository.findById(snapshotKey)
                .filter(entry -> EXTRACTOR_VERSION.equals(entry.getExtractorVersion()))
                .filter(entry -> sourceHash.equals(entry.getSourceHash()))
                .flatMap(this::deserialize);

        if (cached.isPresent()) {
            log.info("💾 Returning cached company profile for {} ({})", ticker, normalizedReportType);
            return cached.get();
        }

        CompanyProfile extracted = extractor.extract(ticker, normalizedReportType, facts, businessSignals, textEvidence);
        write(snapshotKey, ticker, normalizedReportType, periodLabel, filingDate, sourceHash, extracted);
        return extracted;
    }

    private Optional<CompanyProfile> deserialize(CompanyProfileSnapshotEntry entry) {
        try {
            return Optional.ofNullable(objectMapper.readValue(entry.getProfileJson(), CompanyProfile.class));
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to deserialize company-profile snapshot {}: {}", entry.getSnapshotKey(), e.getMessage());
            repository.deleteById(entry.getSnapshotKey());
            return Optional.empty();
        }
    }

    private void write(String snapshotKey, String ticker, String reportType, String periodLabel, String filingDate,
            String sourceHash, CompanyProfile profile) {
        try {
            Instant now = Instant.now();
            repository.save(CompanyProfileSnapshotEntry.builder()
                    .snapshotKey(snapshotKey)
                    .ticker(ticker.toUpperCase())
                    .reportType(reportType)
                    .periodLabel(periodLabel)
                    .filingDate(filingDate)
                    .sourceHash(sourceHash)
                    .extractorVersion(EXTRACTOR_VERSION)
                    .profileJson(objectMapper.writeValueAsString(profile))
                    .createdAt(now)
                    .updatedAt(now)
                    .build());
        } catch (JsonProcessingException e) {
            log.warn("⚠️ Failed to serialize company-profile snapshot {}: {}", snapshotKey, e.getMessage());
        }
    }

    private String buildSnapshotKey(String ticker, String reportType, String periodLabel, String filingDate,
            String extractorVersion) {
        String safeDate = filingDate == null || filingDate.isBlank() ? "unknown-date" : filingDate;
        return "company-profile:" + ticker.toUpperCase() + ":" + reportType + ":" + safeDate + ":"
                + sanitize(periodLabel) + ":" + sanitize(extractorVersion);
    }

    private String buildSourceHash(String ticker, String reportType, FinancialFacts facts, BusinessSignals businessSignals,
            Map<String, String> textEvidence) {
        Map<String, Object> fingerprint = new LinkedHashMap<>();
        fingerprint.put("ticker", ticker.toUpperCase());
        fingerprint.put("reportType", reportType);
        fingerprint.put("period", facts != null ? facts.getPeriod() : null);
        fingerprint.put("filingDate", facts != null ? facts.getFilingDate() : null);
        fingerprint.put("companyName", facts != null ? facts.getCompanyName() : null);
        fingerprint.put("marketSector", facts != null ? facts.getMarketSector() : null);
        fingerprint.put("marketIndustry", facts != null ? facts.getMarketIndustry() : null);
        fingerprint.put("marketBusinessSummary", facts != null ? facts.getMarketBusinessSummary() : null);
        fingerprint.put("businessSignals", businessSignals);
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

    private String sanitize(String value) {
        return value == null ? "unknown-period" : value.replaceAll("[^A-Za-z0-9_-]+", "-");
    }
}
