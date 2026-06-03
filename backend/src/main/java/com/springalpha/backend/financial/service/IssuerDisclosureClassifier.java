package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;

import java.util.List;
import java.util.Locale;

public final class IssuerDisclosureClassifier {

    static final String ISSUER_US_COMMON_EQUITY = "us_common_equity";
    static final String ISSUER_ADR = "adr";
    static final String ISSUER_FOREIGN_ISSUER = "foreign_issuer";
    static final String ISSUER_UNKNOWN = "unknown";

    static final String DISCLOSURE_SEC_PRIMARY = "sec_primary";
    static final String DISCLOSURE_SEC_LIMITED_METRIC_PRIMARY = "sec_limited_metric_primary";
    static final String DISCLOSURE_MARKET_METRIC_PRIMARY = "market_metric_primary";

    private static final String FOREIGN_DISCLOSURE_NOTE = (
            "ADR/foreign issuer disclosure can have limited SEC narrative coverage; "
                    + "structured market metrics and company profile facts are primary evidence.");

    private static final List<String> ADR_KEYWORDS = List.of(
            "adr",
            "american depositary",
            "depositary receipt");

    private IssuerDisclosureClassifier() {
    }

    public static void apply(FinancialFacts facts, MarketSupplementalData supplementalData) {
        if (facts == null) {
            return;
        }

        Classification classification = classify(facts, supplementalData);
        facts.setIssuerType(classification.issuerType());
        facts.setDisclosureProfile(classification.disclosureProfile());
        facts.setDisclosureNote(classification.disclosureNote());
    }

    public static void applyIfMissing(FinancialFacts facts) {
        if (facts == null) {
            return;
        }
        if (!isBlank(facts.getIssuerType())
                && !isBlank(facts.getDisclosureProfile())
                && !isBlank(facts.getDisclosureNote())) {
            return;
        }
        Classification classification = classify(facts, null);
        if (isBlank(facts.getIssuerType())) {
            facts.setIssuerType(classification.issuerType());
        }
        if (isBlank(facts.getDisclosureProfile())) {
            facts.setDisclosureProfile(classification.disclosureProfile());
        }
        if (isBlank(facts.getDisclosureNote())) {
            facts.setDisclosureNote(classification.disclosureNote());
        }
    }

    static Classification classify(FinancialFacts facts, MarketSupplementalData supplementalData) {
        String issuerType = issuerType(facts, supplementalData);
        boolean marketBacked = hasMarketMetrics(facts) || hasMarketSnapshot(supplementalData);
        boolean hasFilingDate = !isBlank(facts == null ? null : facts.getFilingDate());

        if (ISSUER_ADR.equals(issuerType) || ISSUER_FOREIGN_ISSUER.equals(issuerType)) {
            String disclosureProfile = marketBacked
                    ? DISCLOSURE_MARKET_METRIC_PRIMARY
                    : DISCLOSURE_SEC_LIMITED_METRIC_PRIMARY;
            return new Classification(issuerType, disclosureProfile, FOREIGN_DISCLOSURE_NOTE);
        }

        if (hasFilingDate) {
            return new Classification(issuerType, DISCLOSURE_SEC_PRIMARY, null);
        }

        if (marketBacked) {
            return new Classification(issuerType, DISCLOSURE_MARKET_METRIC_PRIMARY, null);
        }

        return new Classification(issuerType, DISCLOSURE_SEC_PRIMARY, null);
    }

    private static String issuerType(FinancialFacts facts, MarketSupplementalData supplementalData) {
        String combined = String.join(" ",
                normalize(value(facts == null ? null : facts.getMarketSecurityType(), supplementalData == null ? null : supplementalData.securityType())),
                normalize(value(facts == null ? null : facts.getMarketQuoteType(), supplementalData == null ? null : supplementalData.quoteType())),
                normalize(value(facts == null ? null : facts.getMarketTypeDisplay(), supplementalData == null ? null : supplementalData.typeDisplay())),
                normalize(value(facts == null ? null : facts.getCompanyName(), supplementalData == null ? null : supplementalData.companyName())));
        if (containsAny(combined, ADR_KEYWORDS)) {
            return ISSUER_ADR;
        }

        String country = value(facts == null ? null : facts.getMarketCountry(), supplementalData == null ? null : supplementalData.country());
        if (!isBlank(country) && !isUnitedStates(country)) {
            return ISSUER_FOREIGN_ISSUER;
        }

        if (combined.isBlank() && isBlank(country)) {
            return ISSUER_UNKNOWN;
        }

        return ISSUER_US_COMMON_EQUITY;
    }

    private static boolean hasMarketMetrics(FinancialFacts facts) {
        if (facts == null) {
            return false;
        }
        return facts.getRevenue() != null
                || facts.getOperatingCashFlow() != null
                || facts.getFreeCashFlow() != null
                || facts.getPriceToEarningsRatio() != null
                || facts.getPriceToBookRatio() != null;
    }

    private static boolean hasMarketSnapshot(MarketSupplementalData supplementalData) {
        return supplementalData != null
                && supplementalData.quarterlyFinancials() != null
                && !supplementalData.quarterlyFinancials().isEmpty();
    }

    private static boolean containsAny(String haystack, List<String> needles) {
        for (String needle : needles) {
            if (!needle.isBlank() && haystack.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isUnitedStates(String country) {
        String normalized = normalize(country);
        return normalized.equals("united states")
                || normalized.equals("usa")
                || normalized.equals("us")
                || normalized.equals("u.s.")
                || normalized.equals("u.s.a.");
    }

    private static String value(String preferred, String fallback) {
        return !isBlank(preferred) ? preferred : fallback;
    }

    private static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT).trim();
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    record Classification(String issuerType, String disclosureProfile, String disclosureNote) {
    }
}
