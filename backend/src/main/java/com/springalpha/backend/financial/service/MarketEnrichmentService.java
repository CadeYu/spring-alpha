package com.springalpha.backend.financial.service;

public interface MarketEnrichmentService {

    MarketSupplementalData getSupplementalData(String ticker, String reportType);
}
