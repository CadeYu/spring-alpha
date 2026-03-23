package com.springalpha.backend.service.profile;

import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Service
public class CompanyProfileExtractor {

    private static final int MAX_ITEMS = 4;
    private static final Pattern SENTENCE_SPLIT_PATTERN = Pattern.compile("(?<=[.!?。！？])\\s+");
    private static final Pattern KPI_PATTERN = Pattern.compile(
            "(?i)\\b(arr|nrr|gmv|take rate|mau|dau|net deposits|platform assets|assets under custody|assets under management|gold subscribers|nii|nim|cet1|bookings|backlog|revenue|gross margin|operating margin|net margin|free cash flow|operating cash flow|eps|roe|roa)\\b");

    public CompanyProfile extract(
            String ticker,
            String reportType,
            FinancialFacts facts,
            BusinessSignals signals,
            Map<String, String> textEvidence) {
        String businessSummary = facts == null ? null : trimToNull(facts.getMarketBusinessSummary());
        String period = facts == null ? null : facts.getPeriod();
        String filingDate = facts == null ? null : facts.getFilingDate();

        LinkedHashSet<String> whatItSells = new LinkedHashSet<>();
        LinkedHashSet<String> customers = new LinkedHashSet<>();
        LinkedHashSet<String> productLines = new LinkedHashSet<>();
        LinkedHashSet<String> keyKpis = new LinkedHashSet<>();
        LinkedHashSet<String> businessTags = new LinkedHashSet<>();
        List<CompanyProfile.SourceRef> sourceRefs = new ArrayList<>();

        inferFromBusinessSummary(businessSummary, whatItSells, customers, productLines, keyKpis, sourceRefs);
        inferFromSignals(signals, productLines, customers, keyKpis, sourceRefs);
        inferFromEvidence(textEvidence, productLines, customers, keyKpis, sourceRefs);
        addMetricFallbackKpis(facts, keyKpis);
        inferBusinessTags(facts, businessSummary, signals, textEvidence, productLines, customers, keyKpis, businessTags);

        String businessModelSummary = buildBusinessModelSummary(
                businessSummary,
                whatItSells,
                customers,
                productLines);
        CompanyProfile.SourceQuality sourceQuality = assessSourceQuality(
                businessSummary,
                whatItSells,
                customers,
                productLines,
                businessModelSummary);
        CompanyProfile.AnalysisMode analysisMode = inferAnalysisMode(facts, businessTags, productLines, customers, keyKpis);
        CompanyProfile.SourceQuality analysisModeConfidence = assessAnalysisModeConfidence(
                analysisMode,
                facts,
                businessTags,
                productLines,
                customers,
                textEvidence);

        return CompanyProfile.builder()
                .ticker(ticker == null ? null : ticker.toUpperCase(Locale.ROOT))
                .reportType(reportType == null ? "quarterly" : reportType)
                .period(period)
                .filingDate(filingDate)
                .whatItSells(limit(whatItSells))
                .customerTypes(limit(customers))
                .productLines(limit(productLines))
                .keyKpis(limit(keyKpis))
                .businessModelSummary(businessModelSummary)
                .sourceQuality(sourceQuality)
                .analysisMode(analysisMode)
                .analysisModeConfidence(analysisModeConfidence)
                .businessTags(limit(businessTags))
                .sourceRefs(sourceRefs.stream().limit(6).toList())
                .build();
    }

    private void inferFromBusinessSummary(
            String businessSummary,
            Set<String> whatItSells,
            Set<String> customers,
            Set<String> productLines,
            Set<String> keyKpis,
            List<CompanyProfile.SourceRef> sourceRefs) {
        if (businessSummary == null) {
            return;
        }

        for (String sentence : splitSentences(businessSummary)) {
            String normalized = sentence.toLowerCase(Locale.ROOT);
            if (containsAny(normalized, "provides", "develops", "designs", "delivers", "offers", "sells")
                    && hasSpecificBusinessSignal(normalized)) {
                addItem(whatItSells, toBusinessPhrase(sentence));
                addRef(sourceRefs, "whatItSells", "Yahoo business summary", sentence);
            }
            if (containsAny(normalized, "customers", "customer", "clients", "enterprises", "consumers", "cloud", "hyperscale",
                    "advertisers", "financial institutions", "institutional", "retail investors", "merchants")) {
                addItems(customers, inferCustomerTypes(sentence));
                addRef(sourceRefs, "customerTypes", "Yahoo business summary", sentence);
            }
            addItems(productLines, inferProductLines(sentence));
            addItems(keyKpis, inferKpis(sentence));
        }
    }

    private void inferFromSignals(
            BusinessSignals signals,
            Set<String> productLines,
            Set<String> customers,
            Set<String> keyKpis,
            List<CompanyProfile.SourceRef> sourceRefs) {
        if (signals == null) {
            return;
        }
        addSignalItems(signals.getProductServiceUpdates(), productLines, customers, keyKpis, sourceRefs, "Business Signals");
        addSignalItems(signals.getSegmentPerformance(), productLines, customers, keyKpis, sourceRefs, "Business Signals");
        addSignalItems(signals.getStrategicMoves(), productLines, customers, keyKpis, sourceRefs, "Business Signals");
    }

    private void addSignalItems(
            List<BusinessSignals.SignalItem> items,
            Set<String> productLines,
            Set<String> customers,
            Set<String> keyKpis,
            List<CompanyProfile.SourceRef> sourceRefs,
            String source) {
        if (items == null) {
            return;
        }
        for (BusinessSignals.SignalItem item : items) {
            String text = firstNonBlank(item.getSummary(), item.getTitle());
            if (text == null) {
                continue;
            }
            addItems(productLines, inferProductLines(text));
            addItems(customers, inferCustomerTypes(text));
            addItems(keyKpis, inferKpis(text));
            if (!inferProductLines(text).isEmpty()) {
                addRef(sourceRefs, "productLines", source, text);
            }
        }
    }

    private void inferFromEvidence(
            Map<String, String> textEvidence,
            Set<String> productLines,
            Set<String> customers,
            Set<String> keyKpis,
            List<CompanyProfile.SourceRef> sourceRefs) {
        if (textEvidence == null || textEvidence.isEmpty()) {
            return;
        }
        for (Map.Entry<String, String> entry : textEvidence.entrySet()) {
            for (String sentence : splitSentences(entry.getValue())) {
                if (sentence.length() < 40) {
                    continue;
                }
                List<String> inferredProducts = inferProductLines(sentence);
                if (!inferredProducts.isEmpty()) {
                    addItems(productLines, inferredProducts);
                    addRef(sourceRefs, "productLines", entry.getKey(), sentence);
                }
                addItems(customers, inferCustomerTypes(sentence));
                addItems(keyKpis, inferKpis(sentence));
            }
        }
    }

    private void addMetricFallbackKpis(FinancialFacts facts, Set<String> keyKpis) {
        if (facts == null) {
            return;
        }
        if (facts.getRevenue() != null) {
            keyKpis.add("Revenue");
        }
        if (facts.getGrossMargin() != null) {
            keyKpis.add("Gross Margin");
        }
        if (facts.getOperatingMargin() != null) {
            keyKpis.add("Operating Margin");
        }
        if (facts.getNetMargin() != null) {
            keyKpis.add("Net Margin");
        }
        if (facts.getFreeCashFlow() != null) {
            keyKpis.add("Free Cash Flow");
        }
        if (facts.getReturnOnEquity() != null) {
            keyKpis.add("ROE");
        }
        if (facts.getReturnOnAssets() != null) {
            keyKpis.add("ROA");
        }
    }

    private void inferBusinessTags(
            FinancialFacts facts,
            String businessSummary,
            BusinessSignals signals,
            Map<String, String> textEvidence,
            Set<String> productLines,
            Set<String> customers,
            Set<String> keyKpis,
            Set<String> businessTags) {
        String combined = buildCombinedContext(facts, businessSummary, signals, textEvidence);
        if (combined == null) {
            return;
        }
        String lower = combined.toLowerCase(Locale.ROOT);
        String industry = trimToNull(facts == null ? null : facts.getMarketIndustry());
        String sector = trimToNull(facts == null ? null : facts.getMarketSector());
        String lowerIndustry = industry == null ? "" : industry.toLowerCase(Locale.ROOT);
        String lowerSector = sector == null ? "" : sector.toLowerCase(Locale.ROOT);

        addIf(businessTags, containsAny(lower,
                "crypto", "cryptocurrency", "digital asset", "blockchain", "stablecoin", "staking", "custody"),
                "crypto");
        addIf(businessTags, containsAny(lower, "crypto exchange", "cryptocurrency exchange", "digital asset trading", "crypto asset trading"),
                "crypto_exchange");
        addIf(businessTags, containsAny(lower, "custody", "custodial"), "custody");
        addIf(businessTags, containsAny(lower, "staking"), "staking");
        addIf(businessTags, containsAny(lower, "stablecoin"), "stablecoin");
        addIf(businessTags, containsAny(lower,
                "digital asset treasury", "crypto treasury", "treasury strategy", "digital asset reserve",
                "crypto reserve", "treasury reserve", "net asset value", "nav per share"),
                "crypto_treasury");
        addIf(businessTags, containsAny(lower,
                "ethereum treasury", "ether treasury", "eth treasury", "ethereum holdings", "ether holdings",
                "accumulating eth", "eth reserve", "ether reserve"),
                "ethereum_treasury");
        addIf(businessTags, containsAny(lower,
                "bitcoin treasury", "btc treasury", "bitcoin holdings", "btc holdings",
                "accumulating bitcoin", "bitcoin reserve", "btc reserve"),
                "bitcoin_treasury");

        addIf(businessTags, containsAny(lower, "advertising", "ads", "advertisers"), "digital_advertising");
        addIf(businessTags, containsAny(lower, "cloud", "google cloud", "azure", "aws"), "cloud");
        addIf(businessTags, containsAny(lower, "youtube"), "youtube");
        addIf(businessTags, containsAny(lower, "search"), "search_platform");
        addIf(businessTags, containsAny(lower, "iphone", "smartphone", "smartphones", "ipad", "mac", "wearables"), "consumer_hardware");
        addIf(businessTags, containsAny(lower, "electric vehicle", "electric vehicles", "vehicle", "vehicles"), "electric_vehicles");
        addIf(businessTags, containsAny(lower, "energy storage", "battery storage"), "energy_storage");
        addIf(businessTags, containsAny(lower, "energy generation", "solar"), "energy_generation");
        addIf(businessTags, containsAny(lower, "serdes", "serializer/deserializer", "active electrical cable", "aec", "optical dsp", "retimer", "pcie", "ethernet"),
                "semiconductor_connectivity");
        addIf(businessTags, isAiConnectivityContext(lower), "ai_connectivity");
        addIf(businessTags, containsAny(lower, "brokerage"), "brokerage");
        addIf(businessTags, containsAny(lower, "event contracts", "index options", "futures"), "derivatives");
        addIf(businessTags, containsAny(lower, "credit card", "payment network", "merchant acquiring"), "payments");
        addIf(businessTags, containsAny(lower, "deposit", "checking", "savings"), "deposit_products");
        addIf(businessTags, containsAny(lower, "asset management", "assets under management", "aum"), "asset_management");
        addIf(businessTags, containsAny(lower, "exchange", "market data", "index provider", "clearing"), "market_infrastructure");
        addIf(businessTags, containsAny(lower, "insurance", "underwriting"), "insurance");
        addIf(businessTags, containsAny(lower, "reit", "real estate investment trust", "rental income"), "reit");
        addIf(businessTags, containsAny(lower, "drug candidate", "clinical trial", "phase 1", "phase 2", "phase 3"), "biotech");
        addIf(businessTags, containsAny(lower, "oil", "gas", "copper", "gold mine", "mining", "commodity"), "commodity_energy");

        addIf(businessTags, lowerIndustry.contains("capital markets") || lowerIndustry.contains("financial exchanges"), "market_infrastructure");
        addIf(businessTags, lowerIndustry.contains("asset management"), "asset_management");
        addIf(businessTags, lowerIndustry.contains("insurance"), "insurance");
        addIf(businessTags, lowerIndustry.contains("reit"), "reit");
        addIf(businessTags, lowerIndustry.contains("semiconductor"), "semiconductor");
        addIf(businessTags, lowerIndustry.contains("communication equipment") || lowerIndustry.contains("networking"), "networking");
        addIf(businessTags, lowerIndustry.contains("internet content"), "internet_platform");
        addIf(businessTags, lowerSector.contains("financial"), "financial_sector");

        if (productLines.contains("Crypto asset trading")) {
            businessTags.add("crypto_exchange");
        }
        if (productLines.contains("Cloud services")) {
            businessTags.add("cloud");
        }
        if (productLines.contains("YouTube")) {
            businessTags.add("youtube");
        }
        if (productLines.contains("Smartphones")) {
            businessTags.add("consumer_hardware");
        }
        if (customers.contains("Advertisers")) {
            businessTags.add("digital_advertising");
        }
        if (keyKpis.contains("Assets Under Management")) {
            businessTags.add("asset_management");
        }
    }

    private CompanyProfile.AnalysisMode inferAnalysisMode(
            FinancialFacts facts,
            Set<String> businessTags,
            Set<String> productLines,
            Set<String> customers,
            Set<String> keyKpis) {
        if (businessTags.contains("reit")) {
            return CompanyProfile.AnalysisMode.REIT;
        }
        if (businessTags.contains("ethereum_treasury") || businessTags.contains("bitcoin_treasury")
                || businessTags.contains("crypto_treasury")) {
            return CompanyProfile.AnalysisMode.CRYPTO_TREASURY;
        }
        if (businessTags.contains("crypto_exchange") || businessTags.contains("custody")
                || businessTags.contains("staking") || businessTags.contains("stablecoin")) {
            return CompanyProfile.AnalysisMode.CRYPTO_EXCHANGE;
        }
        if (businessTags.contains("insurance")) {
            return CompanyProfile.AnalysisMode.INSURANCE;
        }
        if (businessTags.contains("asset_management")) {
            return CompanyProfile.AnalysisMode.ASSET_MANAGER;
        }
        if (businessTags.contains("market_infrastructure")) {
            return CompanyProfile.AnalysisMode.EXCHANGE_MARKET_INFRA;
        }
        if (businessTags.contains("payments")) {
            return CompanyProfile.AnalysisMode.PAYMENT_FINTECH;
        }
        if (businessTags.contains("biotech")
                && (facts == null || facts.getRevenue() == null || facts.getRevenue().signum() <= 0)) {
            return CompanyProfile.AnalysisMode.BIOTECH_PRE_REVENUE;
        }
        if (businessTags.contains("commodity_energy")) {
            return CompanyProfile.AnalysisMode.COMMODITY_ENERGY;
        }
        if (businessTags.contains("semiconductor") || businessTags.contains("semiconductor_connectivity")
                || businessTags.contains("ai_connectivity")) {
            return CompanyProfile.AnalysisMode.SEMICONDUCTOR;
        }
        if (businessTags.contains("networking")) {
            return CompanyProfile.AnalysisMode.TELECOM_NETWORKING;
        }
        if (businessTags.contains("consumer_hardware") || businessTags.contains("digital_advertising")
                || businessTags.contains("cloud") || businessTags.contains("internet_platform")
                || businessTags.contains("electric_vehicles")) {
            return CompanyProfile.AnalysisMode.OPERATING;
        }

        String industry = trimToNull(facts == null ? null : facts.getMarketIndustry());
        String sector = trimToNull(facts == null ? null : facts.getMarketSector());
        String lowerIndustry = industry == null ? "" : industry.toLowerCase(Locale.ROOT);
        String lowerSector = sector == null ? "" : sector.toLowerCase(Locale.ROOT);
        if (containsAny(lowerIndustry, "banks", "credit services", "financial data", "capital markets")
                || lowerSector.contains("financial")) {
            return CompanyProfile.AnalysisMode.FINANCIAL;
        }
        if (!productLines.isEmpty() || !customers.isEmpty() || !keyKpis.isEmpty()) {
            return CompanyProfile.AnalysisMode.OPERATING;
        }
        return CompanyProfile.AnalysisMode.UNKNOWN;
    }

    private CompanyProfile.SourceQuality assessAnalysisModeConfidence(
            CompanyProfile.AnalysisMode analysisMode,
            FinancialFacts facts,
            Set<String> businessTags,
            Set<String> productLines,
            Set<String> customers,
            Map<String, String> textEvidence) {
        if (analysisMode == null || analysisMode == CompanyProfile.AnalysisMode.UNKNOWN) {
            return CompanyProfile.SourceQuality.LOW;
        }

        int score = 0;
        if (analysisMode == CompanyProfile.AnalysisMode.CRYPTO_TREASURY) {
            if (businessTags.contains("ethereum_treasury") || businessTags.contains("bitcoin_treasury")) {
                score += 3;
            }
            if (businessTags.contains("crypto_treasury")) {
                score += 2;
            }
            if (containsTreasuryEvidence(textEvidence)) {
                score += 2;
            }
        } else {
            if (!productLines.isEmpty()) {
                score += 2;
            }
            if (!customers.isEmpty()) {
                score += 1;
            }
            if (!businessTags.isEmpty()) {
                score += 1;
            }
        }

        String industry = trimToNull(facts == null ? null : facts.getMarketIndustry());
        if (industry != null) {
            score += 1;
        }

        if (score >= 5) {
            return CompanyProfile.SourceQuality.HIGH;
        }
        if (score >= 3) {
            return CompanyProfile.SourceQuality.MEDIUM;
        }
        return CompanyProfile.SourceQuality.LOW;
    }

    private boolean containsTreasuryEvidence(Map<String, String> textEvidence) {
        if (textEvidence == null || textEvidence.isEmpty()) {
            return false;
        }
        return textEvidence.values().stream()
                .filter(value -> value != null)
                .map(value -> value.toLowerCase(Locale.ROOT))
                .anyMatch(value -> containsAny(value,
                        "ethereum treasury", "ether treasury", "eth treasury", "bitcoin treasury",
                        "digital asset treasury", "treasury strategy", "eth holdings", "ether holdings",
                        "btc holdings", "bitcoin holdings", "net asset value"));
    }

    private String buildCombinedContext(
            FinancialFacts facts,
            String businessSummary,
            BusinessSignals signals,
            Map<String, String> textEvidence) {
        StringBuilder sb = new StringBuilder();
        appendContext(sb, businessSummary);
        appendContext(sb, facts == null ? null : facts.getMarketIndustry());
        appendContext(sb, facts == null ? null : facts.getMarketSector());
        appendSignalContext(sb, signals == null ? null : signals.getProductServiceUpdates());
        appendSignalContext(sb, signals == null ? null : signals.getSegmentPerformance());
        appendSignalContext(sb, signals == null ? null : signals.getStrategicMoves());
        if (textEvidence != null) {
            textEvidence.values().forEach(value -> appendContext(sb, value));
        }
        String combined = trimToNull(sb.toString());
        return combined == null ? null : combined;
    }

    private void appendSignalContext(StringBuilder sb, List<BusinessSignals.SignalItem> items) {
        if (items == null) {
            return;
        }
        for (BusinessSignals.SignalItem item : items) {
            appendContext(sb, item == null ? null : item.getTitle());
            appendContext(sb, item == null ? null : item.getSummary());
        }
    }

    private void appendContext(StringBuilder sb, String value) {
        String normalized = trimToNull(value);
        if (normalized == null) {
            return;
        }
        if (!sb.isEmpty()) {
            sb.append('\n');
        }
        sb.append(normalized);
    }

    private String buildBusinessModelSummary(
            String businessSummary,
            Set<String> whatItSells,
            Set<String> customers,
            Set<String> productLines) {
        if (businessSummary != null) {
            String firstSentence = splitSentences(businessSummary).stream().findFirst().orElse(null);
            if (firstSentence != null && isSpecificBusinessSummary(firstSentence)) {
                return trimToNull(firstSentence);
            }
        }
        String sells = whatItSells.stream()
                .filter(this::isSpecificBusinessSummary)
                .findFirst()
                .orElse(null);
        String customer = customers.stream()
                .filter(this::isSpecificCustomerType)
                .findFirst()
                .orElse(null);
        String product = productLines.stream()
                .filter(this::isSpecificProductLine)
                .findFirst()
                .orElse(null);
        if (sells == null && product == null) {
            return null;
        }
        if (customer != null) {
            return (sells != null ? sells : product) + " for " + customer;
        }
        return sells != null ? sells : product;
    }

    private String toBusinessPhrase(String sentence) {
        String trimmed = trimToNull(sentence);
        if (trimmed == null) {
            return null;
        }
        trimmed = trimmed.replaceAll("(?i)^the company\\s+", "");
        trimmed = trimmed.replaceAll("(?i)^company\\s+", "");
        return trimmed.length() > 140 ? trimmed.substring(0, 140).trim() : trimmed;
    }

    private List<String> inferProductLines(String text) {
        String lower = text.toLowerCase(Locale.ROOT);
        LinkedHashSet<String> products = new LinkedHashSet<>();
        addIf(products, containsAny(lower, "iphone", "smartphone", "smartphones"), "Smartphones");
        addIf(products, containsAny(lower, "mac", "personal computer", "personal computers", "computer", "computers"), "Personal computers");
        addIf(products, containsAny(lower, "ipad", "tablet", "tablets"), "Tablets");
        addIf(products, containsAny(lower, "wearables", "watch", "airpods"), "Wearables and accessories");
        addIf(products, containsAny(lower, "electric vehicle", "electric vehicles", "vehicle", "vehicles"), "Electric vehicles");
        addIf(products, containsAny(lower, "energy storage", "battery storage"), "Energy storage systems");
        addIf(products, containsAny(lower, "energy generation", "solar"), "Energy generation systems");
        addIf(products, containsAny(lower, "brokerage"), "Brokerage");
        addIf(products, containsAny(lower, "crypto exchange", "cryptocurrency exchange", "digital asset trading", "crypto asset trading"), "Crypto asset trading");
        addIf(products, containsAny(lower, "custody", "custodial"), "Custody");
        addIf(products, containsAny(lower, "staking"), "Staking");
        addIf(products, containsAny(lower, "stablecoin"), "Stablecoin infrastructure");
        addIf(products, containsAny(lower, "serdes", "serializer/deserializer"), "SerDes");
        addIf(products, containsAny(lower, "active electrical cable", "aec"), "AEC");
        addIf(products, containsAny(lower, "optical dsp"), "Optical DSP");
        addIf(products, containsAny(lower, "retimer"), "Retimer");
        addIf(products, containsAny(lower, "pcie"), "PCIe");
        addIf(products, containsAny(lower, "ethernet"), "Ethernet");
        addIf(products, containsAny(lower, "gold subscription", "gold subscribers", "robinhood gold"), "Gold subscription");
        addIf(products, containsAny(lower, "event contracts"), "Event contracts");
        addIf(products, containsAny(lower, "index options"), "Index options");
        addIf(products, containsAny(lower, "futures"), "Futures");
        addIf(products, containsAny(lower, "credit card"), "Credit card");
        addIf(products, containsAny(lower, "checking", "savings", "deposit"), "Deposit products");
        addIf(products, isAiConnectivityContext(lower), "AI data-center connectivity");
        addIf(products, containsAny(lower, "advertising", "ads"), "Advertising");
        addIf(products, containsAny(lower, "google cloud", "cloud services", "cloud platform"), "Cloud services");
        addIf(products, containsAny(lower, "youtube"), "YouTube");
        return limit(products);
    }

    private boolean isAiConnectivityContext(String lower) {
        if (lower == null) {
            return false;
        }
        boolean hasDataCenterContext = containsAny(lower,
                "ai data center",
                "data center interconnect",
                "data-center interconnect",
                "cloud and hyperscale",
                "hyperscale data center",
                "high-speed interconnect");
        boolean hasSemiconductorConnectivityTerms = containsAny(lower,
                "serdes",
                "serializer/deserializer",
                "active electrical cable",
                "aec",
                "optical dsp",
                "retimer",
                "pcie",
                "ethernet");
        return hasDataCenterContext && hasSemiconductorConnectivityTerms;
    }

    private List<String> inferCustomerTypes(String text) {
        String lower = text.toLowerCase(Locale.ROOT);
        LinkedHashSet<String> customers = new LinkedHashSet<>();
        addIf(customers, containsAny(lower, "hyperscale", "hyperscaler"), "Hyperscalers");
        addIf(customers, containsAny(lower, "cloud customers", "cloud providers", "data center customers"), "Cloud and data-center customers");
        addIf(customers, containsAny(lower, "enterprise", "enterprises"), "Enterprise customers");
        addIf(customers,
                containsAny(lower, "retail investors", "retail customers", "retail users")
                        || (lower.contains("retail") && containsAny(lower, "institutional", "crypto", "brokerage", "trading")),
                "Retail investors");
        addIf(customers, containsAny(lower, "advertisers"), "Advertisers");
        addIf(customers, containsAny(lower, "merchant", "merchants"), "Merchants");
        addIf(customers, containsAny(lower, "financial institutions", "banks"), "Financial institutions");
        addIf(customers, containsAny(lower, "institutional", "institutions"), "Institutional customers");
        addIf(customers, containsAny(lower, "network equipment", "switch", "router"), "Networking equipment customers");
        return limit(customers);
    }

    private CompanyProfile.SourceQuality assessSourceQuality(
            String businessSummary,
            Set<String> whatItSells,
            Set<String> customers,
            Set<String> productLines,
            String businessModelSummary) {
        int score = 0;
        String firstSentence = businessSummary == null ? null : splitSentences(businessSummary).stream().findFirst().orElse(null);
        if (isSpecificBusinessSummary(firstSentence)) {
            score += 3;
        }
        if (productLines.stream().anyMatch(this::isSpecificProductLine)) {
            score += 2;
        }
        if (customers.stream().anyMatch(this::isSpecificCustomerType)) {
            score += 1;
        }
        if (whatItSells.stream().anyMatch(this::isSpecificBusinessSummary)) {
            score += 1;
        }
        if (isSpecificBusinessSummary(businessModelSummary)) {
            score += 1;
        }
        if (score >= 4) {
            return CompanyProfile.SourceQuality.HIGH;
        }
        if (score >= 2) {
            return CompanyProfile.SourceQuality.MEDIUM;
        }
        return CompanyProfile.SourceQuality.LOW;
    }

    private boolean isSpecificBusinessSummary(String text) {
        String lower = trimToNull(text);
        return lower != null && hasSpecificBusinessSignal(lower.toLowerCase(Locale.ROOT));
    }

    private boolean hasSpecificBusinessSignal(String lower) {
        if (lower == null) {
            return false;
        }
        if (containsAny(lower,
                "smartphone", "smartphones", "iphone", "mac", "personal computer", "ipad", "tablet", "wearables",
                "electric vehicle", "electric vehicles", "energy storage", "energy generation", "solar",
                "serdes", "serializer/deserializer", "active electrical cable", "aec", "optical dsp", "retimer", "pcie", "ethernet",
                "brokerage", "gold subscription", "event contracts", "index options", "futures",
                "crypto exchange", "cryptocurrency exchange", "digital asset trading", "crypto asset trading", "custody", "staking", "stablecoin",
                "google cloud", "youtube", "advertising", "ads")) {
            return true;
        }
        return containsAny(lower, "search", "advertisers", "cloud") && containsAny(lower, "google", "alphabet", "youtube", "ads");
    }

    private boolean isSpecificProductLine(String productLine) {
        String lower = trimToNull(productLine);
        if (lower == null) {
            return false;
        }
        lower = lower.toLowerCase(Locale.ROOT);
        return !containsAny(lower, "services", "subscriptions");
    }

    private boolean isSpecificCustomerType(String customerType) {
        String lower = trimToNull(customerType);
        if (lower == null) {
            return false;
        }
        lower = lower.toLowerCase(Locale.ROOT);
        return !containsAny(lower, "enterprise customers");
    }

    private List<String> inferKpis(String text) {
        LinkedHashSet<String> kpis = new LinkedHashSet<>();
        Matcher matcher = KPI_PATTERN.matcher(text);
        while (matcher.find()) {
            kpis.add(normalizeKpiLabel(matcher.group()));
        }
        return limit(kpis);
    }

    private String normalizeKpiLabel(String raw) {
        String lower = raw.toLowerCase(Locale.ROOT);
        return switch (lower) {
            case "arr" -> "ARR";
            case "nrr" -> "NRR";
            case "gmv" -> "GMV";
            case "mau" -> "MAU";
            case "dau" -> "DAU";
            case "net deposits" -> "Net Deposits";
            case "platform assets" -> "Platform Assets";
            case "assets under custody" -> "Assets Under Custody";
            case "assets under management" -> "Assets Under Management";
            case "gold subscribers" -> "Gold Subscribers";
            case "nii" -> "NII";
            case "nim" -> "NIM";
            case "cet1" -> "CET1";
            case "take rate" -> "Take Rate";
            case "free cash flow" -> "Free Cash Flow";
            case "operating cash flow" -> "Operating Cash Flow";
            case "gross margin" -> "Gross Margin";
            case "operating margin" -> "Operating Margin";
            case "net margin" -> "Net Margin";
            case "roe" -> "ROE";
            case "roa" -> "ROA";
            case "eps" -> "EPS";
            default -> titleCase(raw);
        };
    }

    private String titleCase(String value) {
        String[] parts = value.toLowerCase(Locale.ROOT).split("\\s+");
        StringBuilder sb = new StringBuilder();
        for (String part : parts) {
            if (part.isBlank()) {
                continue;
            }
            if (!sb.isEmpty()) {
                sb.append(' ');
            }
            sb.append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
        }
        return sb.toString();
    }

    private List<String> splitSentences(String text) {
        String normalized = trimToNull(text);
        if (normalized == null) {
            return List.of();
        }
        return List.of(SENTENCE_SPLIT_PATTERN.split(normalized));
    }

    private boolean containsAny(String haystack, String... needles) {
        for (String needle : needles) {
            if (haystack.contains(needle)) {
                return true;
            }
        }
        return false;
    }

    private void addRef(List<CompanyProfile.SourceRef> refs, String field, String source, String excerpt) {
        if (excerpt == null || excerpt.isBlank()) {
            return;
        }
        refs.add(CompanyProfile.SourceRef.builder()
                .field(field)
                .source(source)
                .excerpt(excerpt.length() > 180 ? excerpt.substring(0, 180).trim() : excerpt.trim())
                .build());
    }

    private void addItem(Set<String> target, String value) {
        String normalized = trimToNull(value);
        if (normalized != null) {
            target.add(normalized);
        }
    }

    private void addItems(Set<String> target, List<String> values) {
        if (values == null) {
            return;
        }
        values.forEach(value -> addItem(target, value));
    }

    private void addIf(Set<String> target, boolean condition, String value) {
        if (condition) {
            addItem(target, value);
        }
    }

    private List<String> limit(Set<String> values) {
        return values.stream().limit(MAX_ITEMS).toList();
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim().replaceAll("\\s+", " ");
        return trimmed.isBlank() ? null : trimmed;
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            String normalized = trimToNull(value);
            if (normalized != null) {
                return normalized;
            }
        }
        return null;
    }
}
