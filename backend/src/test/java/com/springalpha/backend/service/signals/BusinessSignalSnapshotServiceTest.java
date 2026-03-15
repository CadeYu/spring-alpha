package com.springalpha.backend.service.signals;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class BusinessSignalSnapshotServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void cacheHitReturnsStoredSignalsJsonWithoutReextracting() throws Exception {
        BusinessSignalSnapshotRepository repository = mock(BusinessSignalSnapshotRepository.class);
        BusinessSignalExtractor extractor = mock(BusinessSignalExtractor.class);
        BusinessSignalSnapshotService service = new BusinessSignalSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts("Q2 2026", "2026-01-31");
        Map<String, String> evidence = Map.of("MD&A", "Azure growth remained strong.");

        BusinessSignals storedSignals = sampleSignals("quarterly");
        when(repository.findById("signals:MSFT:quarterly:2026-01-31:Q2-2026:v3"))
                .thenReturn(Optional.of(snapshotEntry(
                        "signals:MSFT:quarterly:2026-01-31:Q2-2026:v3",
                        "quarterly",
                        expectedSourceHash("MSFT", "quarterly", facts, evidence, true),
                        objectMapper.writeValueAsString(storedSignals))));

        BusinessSignals result = service.getOrExtract(
                "MSFT",
                "quarterly",
                facts,
                evidence,
                true);

        assertEquals(storedSignals.getEvidenceRefs().get(0).getExcerpt(), result.getEvidenceRefs().get(0).getExcerpt());
        verify(extractor, never()).extract(anyString(), anyString(), any(), any());
        verify(repository, never()).save(any());
    }

    @Test
    void cacheMissExtractsAndPersistsSnapshotWithVersionedKey() {
        BusinessSignalSnapshotRepository repository = mock(BusinessSignalSnapshotRepository.class);
        BusinessSignalExtractor extractor = mock(BusinessSignalExtractor.class);
        BusinessSignalSnapshotService service = new BusinessSignalSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts("Q2 2026", "2026-01-31");
        Map<String, String> evidence = Map.of("MD&A", "Azure growth remained strong.");
        BusinessSignals extractedSignals = sampleSignals("quarterly");

        when(repository.findById(anyString())).thenReturn(Optional.empty());
        when(extractor.extract("MSFT", "quarterly", facts, evidence)).thenReturn(extractedSignals);

        BusinessSignals result = service.getOrExtract("MSFT", "quarterly", facts, evidence, true);

        assertSame(extractedSignals, result);

        ArgumentCaptor<BusinessSignalSnapshotEntry> captor = ArgumentCaptor.forClass(BusinessSignalSnapshotEntry.class);
        verify(repository).save(captor.capture());
        assertEquals("signals:MSFT:quarterly:2026-01-31:Q2-2026:v3", captor.getValue().getSnapshotKey());
        assertEquals("quarterly", captor.getValue().getReportType());
        assertEquals("2026-01-31", captor.getValue().getFilingDate());
        assertNotNull(captor.getValue().getSignalsJson());
    }

    @Test
    void malformedSnapshotPayloadIsDroppedAndRebuilt() {
        BusinessSignalSnapshotRepository repository = mock(BusinessSignalSnapshotRepository.class);
        BusinessSignalExtractor extractor = mock(BusinessSignalExtractor.class);
        BusinessSignalSnapshotService service = new BusinessSignalSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts("Q2 2026", "2026-01-31");
        Map<String, String> evidence = Map.of("MD&A", "Azure growth remained strong.");
        String snapshotKey = "signals:MSFT:quarterly:2026-01-31:Q2-2026:v3";

        when(repository.findById(snapshotKey))
                .thenReturn(Optional.of(snapshotEntry(
                        snapshotKey,
                        "quarterly",
                        expectedSourceHash("MSFT", "quarterly", facts, evidence, true),
                        "{bad json")));
        when(extractor.extract("MSFT", "quarterly", facts, evidence)).thenReturn(sampleSignals("quarterly"));

        BusinessSignals result = service.getOrExtract("MSFT", "quarterly", facts, evidence, true);

        assertNotNull(result);
        verify(repository).deleteById(snapshotKey);
        verify(repository).save(any(BusinessSignalSnapshotEntry.class));
    }

    @Test
    void cachedSnapshotsWithMachineReadableArtifactsAreDroppedAndRebuilt() throws Exception {
        BusinessSignalSnapshotRepository repository = mock(BusinessSignalSnapshotRepository.class);
        BusinessSignalExtractor extractor = spy(new BusinessSignalExtractor());
        BusinessSignalSnapshotService service = new BusinessSignalSnapshotService(repository, extractor, objectMapper);
        FinancialFacts facts = sampleFacts("Q2 2026", "2026-01-31");
        Map<String, String> evidence = Map.of("Risk Factors", "Regulatory scrutiny could pressure profitability.");
        String snapshotKey = "signals:JPM:quarterly:2026-01-31:Q2-2026:v3";

        BusinessSignals pollutedSignals = BusinessSignals.builder()
                .ticker("JPM")
                .reportType("quarterly")
                .riskSignals(java.util.List.of(BusinessSignals.SignalItem.builder()
                        .title("需求与定价")
                        .summary("ricingModelMembersrt:WeightedAverageMemberjpm:MeasurementInputCorrelationofInterestRatestoForeignExchangeRatesMember2025-09-300000019617us-gaap:FairValueInputsLevel3Member")
                        .evidenceSection("Risk Factors")
                        .evidenceSnippet("us-gaap:FairValueInputsLevel3Member")
                        .build()))
                .build();
        BusinessSignals rebuiltSignals = sampleSignals("quarterly");

        when(repository.findById(snapshotKey))
                .thenReturn(Optional.of(snapshotEntry(
                        snapshotKey,
                        "quarterly",
                        expectedSourceHash("JPM", "quarterly", facts, evidence, true),
                        objectMapper.writeValueAsString(pollutedSignals))));
        doReturn(rebuiltSignals).when(extractor).extract("JPM", "quarterly", facts, evidence);

        BusinessSignals result = service.getOrExtract("JPM", "quarterly", facts, evidence, true);

        assertSame(rebuiltSignals, result);
        verify(repository).deleteById(snapshotKey);
        verify(repository).save(any(BusinessSignalSnapshotEntry.class));
    }

    @Test
    void distinctFilingsRemainDistinctEvenWhenReportTypeIsNormalizedToQuarterly() {
        BusinessSignalSnapshotRepository repository = mock(BusinessSignalSnapshotRepository.class);
        BusinessSignalExtractor extractor = mock(BusinessSignalExtractor.class);
        BusinessSignalSnapshotService service = new BusinessSignalSnapshotService(repository, extractor, objectMapper);

        when(repository.findById(anyString())).thenReturn(Optional.empty());
        when(extractor.extract(eq("MSFT"), anyString(), any(), any()))
                .thenAnswer(invocation -> sampleSignals(invocation.getArgument(1, String.class)));

        service.getOrExtract("MSFT", "quarterly", sampleFacts("Q2 2026", "2026-01-31"), Map.of(), false);
        service.getOrExtract("MSFT", "annual", sampleFacts("FY 2025", "2026-07-31"), Map.of(), false);

        ArgumentCaptor<BusinessSignalSnapshotEntry> captor = ArgumentCaptor.forClass(BusinessSignalSnapshotEntry.class);
        verify(repository, times(2)).save(captor.capture());

        assertEquals(2, captor.getAllValues().size());
        String quarterlyKey = captor.getAllValues().get(0).getSnapshotKey();
        String annualKey = captor.getAllValues().get(1).getSnapshotKey();
        assertNotEquals(quarterlyKey, annualKey);
        assertTrue(quarterlyKey.contains(":quarterly:"));
        assertTrue(annualKey.contains(":quarterly:"));
        assertTrue(quarterlyKey.endsWith(":v3"));
        assertTrue(annualKey.endsWith(":v3"));
    }

    private BusinessSignalSnapshotEntry snapshotEntry(String snapshotKey, String reportType, String sourceHash,
            String signalsJson) {
        return BusinessSignalSnapshotEntry.builder()
                .snapshotKey(snapshotKey)
                .ticker("MSFT")
                .reportType(reportType)
                .periodLabel("Q2 2026")
                .filingDate("2026-01-31")
                .sourceHash(sourceHash)
                .extractorVersion("v3")
                .signalsJson(signalsJson)
                .createdAt(Instant.parse("2026-03-11T00:00:00Z"))
                .updatedAt(Instant.parse("2026-03-11T00:00:00Z"))
                .build();
    }

    private String expectedSourceHash(String ticker, String reportType, FinancialFacts facts, Map<String, String> textEvidence,
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
        } catch (Exception e) {
            throw new IllegalStateException(e);
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
            throw new IllegalStateException(e);
        }
    }

    private BusinessSignals sampleSignals(String reportType) {
        return BusinessSignals.builder()
                .ticker("MSFT")
                .reportType(reportType)
                .period("Q2 2026")
                .filingDate("2026-01-31")
                .segmentPerformance(java.util.List.of(BusinessSignals.SignalItem.builder()
                        .title("Azure / cloud momentum")
                        .summary("Azure revenue grew as AI demand remained strong.")
                        .evidenceSection("MD&A")
                        .evidenceSnippet("Azure revenue grew as AI demand remained strong.")
                        .build()))
                .evidenceRefs(java.util.List.of(BusinessSignals.EvidenceRef.builder()
                        .topic("Azure / cloud momentum")
                        .section("MD&A")
                        .excerpt("Azure revenue grew as AI demand remained strong.")
                        .build()))
                .build();
    }

    private FinancialFacts sampleFacts(String period, String filingDate) {
        return FinancialFacts.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period(period)
                .filingDate(filingDate)
                .revenue(new BigDecimal("100"))
                .revenueYoY(new BigDecimal("0.10"))
                .grossMargin(new BigDecimal("0.50"))
                .netMargin(new BigDecimal("0.25"))
                .build();
    }
}
