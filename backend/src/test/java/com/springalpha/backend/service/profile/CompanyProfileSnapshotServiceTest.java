package com.springalpha.backend.service.profile;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

class CompanyProfileSnapshotServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void cacheHitReturnsStoredProfileWithoutReextracting() throws Exception {
        CompanyProfileSnapshotRepository repository = mock(CompanyProfileSnapshotRepository.class);
        CompanyProfileExtractor extractor = mock(CompanyProfileExtractor.class);
        CompanyProfileSnapshotService service = new CompanyProfileSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts();
        BusinessSignals signals = sampleSignals();
        CompanyProfile stored = CompanyProfile.builder()
                .ticker("CRDO")
                .reportType("quarterly")
                .businessModelSummary("Connectivity solutions for cloud customers")
                .build();
        Map<String, String> textEvidence = Map.of("MD&A", "signal");

        when(repository.findById("company-profile:CRDO:quarterly:2026-03-01:FY2026-Q3:v5"))
                .thenReturn(Optional.of(snapshotEntry(
                        "company-profile:CRDO:quarterly:2026-03-01:FY2026-Q3:v5",
                        objectMapper.writeValueAsString(stored),
                        expectedSourceHash("CRDO", "quarterly", facts, signals, textEvidence))));

        CompanyProfile result = service.getOrExtract("CRDO", "quarterly", facts, signals, textEvidence);

        assertEquals("Connectivity solutions for cloud customers", result.getBusinessModelSummary());
        verify(extractor, never()).extract(anyString(), anyString(), any(), any(), any());
    }

    @Test
    void cacheMissExtractsAndPersistsProfileSnapshot() {
        CompanyProfileSnapshotRepository repository = mock(CompanyProfileSnapshotRepository.class);
        CompanyProfileExtractor extractor = mock(CompanyProfileExtractor.class);
        CompanyProfileSnapshotService service = new CompanyProfileSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts();
        BusinessSignals signals = sampleSignals();
        CompanyProfile extracted = CompanyProfile.builder()
                .ticker("CRDO")
                .reportType("quarterly")
                .productLines(java.util.List.of("SerDes"))
                .build();

        when(repository.findById(anyString())).thenReturn(Optional.empty());
        when(extractor.extract("CRDO", "quarterly", facts, signals, Map.of("MD&A", "signal")))
                .thenReturn(extracted);

        CompanyProfile result = service.getOrExtract("CRDO", "quarterly", facts, signals, Map.of("MD&A", "signal"));

        assertSame(extracted, result);
        ArgumentCaptor<CompanyProfileSnapshotEntry> captor = ArgumentCaptor.forClass(CompanyProfileSnapshotEntry.class);
        verify(repository).save(captor.capture());
        assertEquals("company-profile:CRDO:quarterly:2026-03-01:FY2026-Q3:v5", captor.getValue().getSnapshotKey());
    }

    private FinancialFacts sampleFacts() {
        return FinancialFacts.builder()
                .ticker("CRDO")
                .period("FY2026 Q3")
                .filingDate("2026-03-01")
                .marketBusinessSummary("Credo develops connectivity solutions for cloud customers.")
                .build();
    }

    private BusinessSignals sampleSignals() {
        return BusinessSignals.builder()
                .ticker("CRDO")
                .reportType("quarterly")
                .build();
    }

    private CompanyProfileSnapshotEntry snapshotEntry(String snapshotKey, String profileJson, String sourceHash) {
        return CompanyProfileSnapshotEntry.builder()
                .snapshotKey(snapshotKey)
                .ticker("CRDO")
                .reportType("quarterly")
                .periodLabel("FY2026 Q3")
                .filingDate("2026-03-01")
                .sourceHash(sourceHash)
                .extractorVersion("v5")
                .profileJson(profileJson)
                .createdAt(Instant.parse("2026-03-15T00:00:00Z"))
                .updatedAt(Instant.parse("2026-03-15T00:00:00Z"))
                .build();
    }

    private String expectedSourceHash(String ticker, String reportType, FinancialFacts facts, BusinessSignals signals,
            Map<String, String> textEvidence) throws Exception {
        Map<String, Object> fingerprint = new LinkedHashMap<>();
        fingerprint.put("ticker", ticker.toUpperCase());
        fingerprint.put("reportType", reportType);
        fingerprint.put("period", facts != null ? facts.getPeriod() : null);
        fingerprint.put("filingDate", facts != null ? facts.getFilingDate() : null);
        fingerprint.put("companyName", facts != null ? facts.getCompanyName() : null);
        fingerprint.put("marketSector", facts != null ? facts.getMarketSector() : null);
        fingerprint.put("marketIndustry", facts != null ? facts.getMarketIndustry() : null);
        fingerprint.put("marketBusinessSummary", facts != null ? facts.getMarketBusinessSummary() : null);
        fingerprint.put("businessSignals", signals);
        fingerprint.put("textEvidence", textEvidence);
        return sha256(objectMapper.writeValueAsString(fingerprint));
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
            throw new IllegalStateException(e);
        }
    }
}
