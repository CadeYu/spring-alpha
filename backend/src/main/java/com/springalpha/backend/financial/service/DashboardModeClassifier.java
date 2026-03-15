package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;

import java.util.List;
import java.util.Locale;

final class DashboardModeClassifier {

    static final String MODE_STANDARD = "standard";
    static final String MODE_FINANCIAL = "financial_sector";
    static final String MODE_UNSUPPORTED_REIT = "unsupported_reit";

    private static final List<String> REIT_KEYWORDS = List.of(
            "reit",
            "real estate investment trust");

    private static final List<String> BANK_KEYWORDS = List.of(
            "bank",
            "banks",
            "banking",
            "bancorp",
            "banco");

    private DashboardModeClassifier() {
    }

    static DashboardMode classify(FinancialFacts facts, MarketSupplementalData supplementalData) {
        String companyName = facts == null ? null : facts.getCompanyName();
        String sector = supplementalData == null ? null : supplementalData.sector();
        String industry = supplementalData == null ? null : supplementalData.industry();
        String securityType = supplementalData == null ? null : supplementalData.securityType();

        String combined = String.join(" ",
                normalize(companyName),
                normalize(sector),
                normalize(industry),
                normalize(securityType));

        if (containsAny(combined, REIT_KEYWORDS)) {
            return new DashboardMode(
                    MODE_UNSUPPORTED_REIT,
                    "This ticker is categorized as a REIT / trust-like issuer, which is outside the current operating-company analysis flow.");
        }

        if (containsAny(combined, BANK_KEYWORDS)) {
            return new DashboardMode(
                    MODE_FINANCIAL,
                    "Financial sector mode is active for this ticker because generic operating-company margin and cash-conversion dashboards are not reliable for bank-style filings.");
        }

        return new DashboardMode(MODE_STANDARD, null);
    }

    private static boolean containsAny(String haystack, List<String> needles) {
        for (String needle : needles) {
            if (!needle.isBlank() && haystack.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
    }

    record DashboardMode(String mode, String message) {
        boolean isUnsupportedReit() {
            return MODE_UNSUPPORTED_REIT.equals(mode);
        }
    }
}
