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
        List<CompanyProfile.SourceRef> sourceRefs = new ArrayList<>();

        inferFromBusinessSummary(businessSummary, whatItSells, customers, productLines, keyKpis, sourceRefs);
        inferFromSignals(signals, productLines, customers, keyKpis, sourceRefs);
        inferFromEvidence(textEvidence, productLines, customers, keyKpis, sourceRefs);
        addMetricFallbackKpis(facts, keyKpis);

        String businessModelSummary = buildBusinessModelSummary(
                businessSummary,
                whatItSells,
                customers,
                productLines);

        return CompanyProfile.builder()
                .ticker(ticker == null ? null : ticker.toUpperCase(Locale.ROOT))
                .reportType("quarterly")
                .period(period)
                .filingDate(filingDate)
                .whatItSells(limit(whatItSells))
                .customerTypes(limit(customers))
                .productLines(limit(productLines))
                .keyKpis(limit(keyKpis))
                .businessModelSummary(businessModelSummary)
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
            if (containsAny(normalized, "provides", "develops", "designs", "delivers", "offers", "sells")) {
                addItem(whatItSells, toBusinessPhrase(sentence));
                addRef(sourceRefs, "whatItSells", "Yahoo business summary", sentence);
            }
            if (containsAny(normalized, "customers", "customer", "clients", "enterprises", "consumers", "cloud", "hyperscale", "advertisers", "financial institutions")) {
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

    private String buildBusinessModelSummary(
            String businessSummary,
            Set<String> whatItSells,
            Set<String> customers,
            Set<String> productLines) {
        if (businessSummary != null) {
            String firstSentence = splitSentences(businessSummary).stream().findFirst().orElse(null);
            if (firstSentence != null) {
                return trimToNull(firstSentence);
            }
        }
        String sells = whatItSells.stream().findFirst().orElse(null);
        String customer = customers.stream().findFirst().orElse(null);
        String product = productLines.stream().findFirst().orElse(null);
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
        addIf(products, containsAny(lower, "services", "service"), "Services");
        addIf(products, containsAny(lower, "electric vehicle", "electric vehicles", "vehicle", "vehicles"), "Electric vehicles");
        addIf(products, containsAny(lower, "energy storage", "battery storage"), "Energy storage systems");
        addIf(products, containsAny(lower, "energy generation", "solar"), "Energy generation systems");
        addIf(products, containsAny(lower, "brokerage"), "Brokerage");
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
        addIf(products, containsAny(lower, "subscription", "subscriptions"), "Subscriptions");
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
        return hasDataCenterContext || hasSemiconductorConnectivityTerms;
    }

    private List<String> inferCustomerTypes(String text) {
        String lower = text.toLowerCase(Locale.ROOT);
        LinkedHashSet<String> customers = new LinkedHashSet<>();
        addIf(customers, containsAny(lower, "hyperscale", "hyperscaler"), "Hyperscalers");
        addIf(customers, containsAny(lower, "cloud customers", "cloud providers", "data center customers"), "Cloud and data-center customers");
        addIf(customers, containsAny(lower, "enterprise", "enterprises"), "Enterprise customers");
        addIf(customers, containsAny(lower, "consumer", "consumers", "retail investors"), "Consumers / retail users");
        addIf(customers, containsAny(lower, "advertisers", "merchant"), "Advertisers / merchants");
        addIf(customers, containsAny(lower, "financial institutions", "banks"), "Financial institutions");
        addIf(customers, containsAny(lower, "network equipment", "switch", "router"), "Networking equipment customers");
        return limit(customers);
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
