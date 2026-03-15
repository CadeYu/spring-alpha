package com.springalpha.backend.service.signals;

import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;
import java.util.regex.Pattern;

@Service
public class BusinessSignalExtractor {

    private static final int MAX_SIGNALS_PER_CATEGORY = 3;
    private static final int MAX_EVIDENCE_REFS = 5;
    private static final Pattern KNOWN_XBRL_NAMESPACE_PATTERN = Pattern.compile(
            "(?i)(?:us-gaap|dei|srt|xbrli|jpm):");
    private static final Pattern XBRL_NAMESPACE_CHAIN_PATTERN = Pattern.compile(
            "(?i)(?:[a-z][a-z0-9_-]{1,20}:){2,}");
    private static final Pattern XBRL_ARTIFACT_TERM_PATTERN = Pattern.compile(
            "(?i)(?:LineItems|Abstract|Axis|Domain|Member|Table|TextBlock|ValuationTechnique|MeasurementInput)");

    public BusinessSignals extract(String ticker, String reportType, FinancialFacts facts, Map<String, String> textEvidence) {
        List<SentenceCandidate> candidates = collectCandidates(textEvidence);

        List<BusinessSignals.SignalItem> segmentPerformance = pickSignals(
                candidates,
                sentence -> containsAny(sentence,
                        "segment", "segments", "advertising", "ads", "azure", "cloud",
                        "reality labs", "family of apps", "services", "iphone", "mac",
                        "ipad", "wearables", "office", "dynamics", "linkedin", "gaming",
                        "subscriptions", "commerce", "energy generation", "storage",
                        "impressions", "pricing", "ad pricing", "ad load", "engagement",
                        "usage", "demand", "bookings", "backlog", "business messaging",
                        "serdes", "aec", "active electrical cable", "optical dsp", "retimer",
                        "ethernet", "pcie", "hyperscaler", "data center interconnect", "connectivity"),
                "业务线 / 分部表现");

        List<BusinessSignals.SignalItem> productServiceUpdates = pickSignals(
                candidates,
                sentence -> containsAny(sentence,
                        "launch", "launched", "released", "introduced", "rollout", "roadmap",
                        "product", "service", "feature", "copilot", "meta ai", "threads",
                        "reels", "business messaging", "recommendation", "ranking",
                        "monetization", "commercialization", "assistant", "subscription",
                        "renewal", "adoption", "广告", "产品", "服务", "功能", "推出", "发布",
                        "serdes", "aec", "active electrical cable", "optical dsp", "retimer",
                        "ethernet", "pcie", "chiplet", "interconnect"),
                "产品与服务进展");

        List<BusinessSignals.SignalItem> managementFocus = pickSignals(
                candidates,
                sentence -> containsAny(sentence,
                        "focus", "focused", "prioritize", "priority", "continue to", "continue investing",
                        "management", "executive", "discipline", "efficiency", "optimiz",
                        "pricing", "mix", "execution", "capacity", "investment", "我们将",
                        "重点", "优先", "管理层", "效率", "纪律"),
                "管理层强调点");

        List<BusinessSignals.SignalItem> strategicMoves = pickSignals(
                candidates,
                sentence -> containsAny(sentence,
                        "strategy", "strategic", "investment", "acquisition", "buyback",
                        "repurchase", "partnership", "monetization", "commercialization",
                        "platform", "ecosystem", "ai", "infrastructure", "data center",
                        "meta ai", "business messaging", "recommendation", "roadmap", "战略",
                        "投资", "回购", "生态", "商业化", "serdes", "aec", "optical dsp",
                        "retimer", "ethernet", "pcie", "customer ramp", "hyperscaler"),
                "战略动作");

        List<BusinessSignals.SignalItem> capexSignals = pickSignals(
                candidates,
                sentence -> containsAny(sentence,
                        "capital expenditure", "capex", "infrastructure", "server", "gpu",
                        "data center", "facility", "compute", "cluster", "capacity",
                        "silicon", "rack", "算力", "资本开支", "数据中心"),
                "资本开支与投资方向");

        List<BusinessSignals.SignalItem> riskSignals = pickSignals(
                candidates,
                sentence -> sentence.section().toLowerCase(Locale.ROOT).contains("risk")
                        || containsAny(sentence,
                                "competition", "competitive", "macro", "regulatory", "privacy",
                                "cyber", "supply chain", "foreign exchange", "tariff",
                                "litigation", "demand", "price pressure", "ad spend",
                                "capacity constraint", "slowdown", "竞争", "宏观",
                                "监管", "隐私", "供应链", "诉讼", "风险"),
                "风险与竞争信号");

        if (managementFocus.isEmpty()) {
            managementFocus = buildFactsFallback(facts);
        }
        if (riskSignals.isEmpty()) {
            riskSignals = buildRiskFallback(facts);
        }

        return BusinessSignals.builder()
                .ticker(ticker)
                .reportType("quarterly")
                .period(facts != null ? facts.getPeriod() : null)
                .filingDate(facts != null ? facts.getFilingDate() : null)
                .segmentPerformance(segmentPerformance)
                .productServiceUpdates(productServiceUpdates)
                .managementFocus(managementFocus)
                .strategicMoves(strategicMoves)
                .capexSignals(capexSignals)
                .riskSignals(riskSignals)
                .evidenceRefs(buildEvidenceRefs(segmentPerformance, productServiceUpdates, strategicMoves, riskSignals))
                .build();
    }

    private List<SentenceCandidate> collectCandidates(Map<String, String> textEvidence) {
        if (textEvidence == null || textEvidence.isEmpty()) {
            return List.of();
        }

        List<SentenceCandidate> candidates = new ArrayList<>();
        textEvidence.forEach((section, value) -> {
            if (value == null || value.isBlank()) {
                return;
            }
            for (String line : value.split("\\R")) {
                String normalizedLine = normalizeWhitespace(line);
                if (normalizedLine.isBlank() || isLowSignalLine(normalizedLine)) {
                    continue;
                }
                for (String sentence : splitIntoSentences(normalizedLine)) {
                    String normalizedSentence = normalizeWhitespace(sentence);
                    if (normalizedSentence.length() < 35 || isLowSignalLine(normalizedSentence)) {
                        continue;
                    }
                    candidates.add(new SentenceCandidate(section, normalizedSentence));
                }
            }
        });
        return candidates;
    }

    private List<BusinessSignals.SignalItem> pickSignals(List<SentenceCandidate> candidates,
            Predicate<SentenceCandidate> predicate,
            String fallbackTitle) {
        List<BusinessSignals.SignalItem> results = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();

        for (SentenceCandidate candidate : candidates) {
            if (!predicate.test(candidate)) {
                continue;
            }
            String normalized = candidate.text().toLowerCase(Locale.ROOT);
            if (!seen.add(normalized)) {
                continue;
            }
            results.add(BusinessSignals.SignalItem.builder()
                    .title(inferTitle(candidate.text(), fallbackTitle))
                    .summary(trim(candidate.text(), 220))
                    .evidenceSection(candidate.section())
                    .evidenceSnippet(trim(candidate.text(), 160))
                    .build());
            if (results.size() >= MAX_SIGNALS_PER_CATEGORY) {
                break;
            }
        }

        return results;
    }

    private List<BusinessSignals.EvidenceRef> buildEvidenceRefs(List<BusinessSignals.SignalItem>... groups) {
        List<BusinessSignals.EvidenceRef> refs = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (List<BusinessSignals.SignalItem> group : groups) {
            if (group == null) {
                continue;
            }
            for (BusinessSignals.SignalItem item : group) {
                String key = item.getTitle() + "::" + item.getEvidenceSnippet();
                if (!seen.add(key)) {
                    continue;
                }
                refs.add(BusinessSignals.EvidenceRef.builder()
                        .topic(item.getTitle())
                        .section(item.getEvidenceSection())
                        .excerpt(item.getEvidenceSnippet())
                        .build());
                if (refs.size() >= MAX_EVIDENCE_REFS) {
                    return refs;
                }
            }
        }
        return refs;
    }

    private List<BusinessSignals.SignalItem> buildFactsFallback(FinancialFacts facts) {
        if (facts == null) {
            return List.of();
        }

        List<BusinessSignals.SignalItem> fallback = new ArrayList<>();
        if (facts.getRevenueYoY() != null) {
            String direction = facts.getRevenueYoY().signum() >= 0 ? "核心需求仍有韧性" : "核心需求仍在调整";
            fallback.add(BusinessSignals.SignalItem.builder()
                    .title(direction)
                    .summary(facts.getRevenueYoY().signum() >= 0
                            ? "Even without richer narrative detail, the reported growth profile suggests the company still has enough demand and mix support to keep the current business plan on track."
                            : "Without richer narrative evidence, the reported growth slowdown suggests management is still working through a softer demand and mix backdrop.")
                    .evidenceSection("Financial Facts")
                    .evidenceSnippet("Revenue YoY from Financial Facts")
                    .build());
        }

        if (facts.getOperatingCashFlowYoY() != null) {
            String direction = facts.getOperatingCashFlowYoY().signum() >= 0
                    ? "投资空间仍在"
                    : "投资节奏面临约束";
            fallback.add(BusinessSignals.SignalItem.builder()
                    .title(direction)
                    .summary(facts.getOperatingCashFlowYoY().signum() >= 0
                            ? "Cash generation still appears strong enough to preserve room for product, go-to-market, or infrastructure investment."
                            : "Cash generation looks tighter, so management may have less room to keep pressing on investment without tougher trade-offs.")
                    .evidenceSection("Financial Facts")
                    .evidenceSnippet("Operating cash flow YoY from Financial Facts")
                    .build());
        }

        return fallback;
    }

    private List<BusinessSignals.SignalItem> buildRiskFallback(FinancialFacts facts) {
        if (facts == null || facts.getNetMargin() == null) {
            return List.of();
        }

        String riskTone = facts.getNetMargin().compareTo(new BigDecimal("0.10")) < 0
                ? "利润率缓冲有限"
                : "投入兑现仍需验证";
        return List.of(BusinessSignals.SignalItem.builder()
                .title(riskTone)
                .summary(facts.getNetMargin().compareTo(new BigDecimal("0.10")) < 0
                        ? "With limited narrative detail, the main risk is that thinner profit buffers leave less room to absorb weaker pricing, mix, or demand."
                        : "When narrative evidence is sparse, the next question is whether management can keep funding its priorities without letting margins or demand momentum slip.")
                .evidenceSection("Financial Facts")
                .evidenceSnippet("Net margin from Financial Facts")
                .build());
    }

    private boolean containsAny(SentenceCandidate candidate, String... keywords) {
        String haystack = candidate.text().toLowerCase(Locale.ROOT);
        for (String keyword : keywords) {
            if (haystack.contains(keyword.toLowerCase(Locale.ROOT))) {
                return true;
            }
        }
        return false;
    }

    private String inferTitle(String sentence, String fallbackTitle) {
        Map<String, String> titleMap = new LinkedHashMap<>();
        titleMap.put("azure", "Azure / cloud momentum");
        titleMap.put("cloud", "Cloud demand");
        titleMap.put("copilot", "Copilot commercialization");
        titleMap.put("meta ai", "Meta AI commercialization");
        titleMap.put("business messaging", "Business messaging monetization");
        titleMap.put("recommendation", "Recommendation efficiency");
        titleMap.put("reels", "Reels monetization");
        titleMap.put("threads", "New platform traction");
        titleMap.put("family of apps", "Family of Apps monetization");
        titleMap.put("advertising", "Advertising engine");
        titleMap.put("ads", "Advertising engine");
        titleMap.put("impressions", "Ad demand and engagement");
        titleMap.put("pricing", "Pricing power");
        titleMap.put("service", "Service mix shift");
        titleMap.put("services", "Service mix shift");
        titleMap.put("subscription", "Subscription retention");
        titleMap.put("renewal", "Renewal behavior");
        titleMap.put("office", "Productivity suite strength");
        titleMap.put("dynamics", "Enterprise application demand");
        titleMap.put("data center", "Infrastructure buildout");
        titleMap.put("data center interconnect", "AI data-center connectivity");
        titleMap.put("connectivity", "High-speed connectivity products");
        titleMap.put("serdes", "SerDes connectivity products");
        titleMap.put("aec", "AEC connectivity products");
        titleMap.put("active electrical cable", "AEC connectivity products");
        titleMap.put("optical dsp", "Optical DSP products");
        titleMap.put("retimer", "Retimer connectivity chips");
        titleMap.put("ethernet", "Ethernet connectivity portfolio");
        titleMap.put("pcie", "PCIe connectivity products");
        titleMap.put("hyperscaler", "Hyperscaler customer ramp");
        titleMap.put("gpu", "GPU capacity");
        titleMap.put("infrastructure", "Infrastructure buildout");
        titleMap.put("reality labs", "Reality Labs investment");
        titleMap.put("capital expenditure", "Capital allocation");
        titleMap.put("capex", "Capital allocation");
        titleMap.put("competition", "Competitive pressure");
        titleMap.put("regulatory", "Regulatory overhang");
        titleMap.put("macro", "Macro sensitivity");

        String lower = sentence.toLowerCase(Locale.ROOT);
        for (Map.Entry<String, String> entry : titleMap.entrySet()) {
            if (lower.contains(entry.getKey())) {
                return entry.getValue();
            }
        }
        return fallbackTitle;
    }

    private boolean isLowSignalLine(String line) {
        return line.contains("[truncated for prompt budget]")
                || line.contains("[additional evidence omitted")
                || line.chars().filter(ch -> ch == '|').count() >= 2
                || line.length() < 20
                || containsMachineReadableArtifact(line);
    }

    boolean containsMachineReadableArtifact(String line) {
        if (line == null || line.isBlank()) {
            return false;
        }

        String normalized = normalizeWhitespace(line);
        String lower = normalized.toLowerCase(Locale.ROOT);
        long whitespaceCount = normalized.chars().filter(Character::isWhitespace).count();
        long colonCount = normalized.chars().filter(ch -> ch == ':').count();

        if (KNOWN_XBRL_NAMESPACE_PATTERN.matcher(lower).find()) {
            return true;
        }

        if (XBRL_NAMESPACE_CHAIN_PATTERN.matcher(lower).find() && whitespaceCount <= 8) {
            return true;
        }

        if (colonCount >= 2 && whitespaceCount <= 8) {
            return true;
        }

        return XBRL_ARTIFACT_TERM_PATTERN.matcher(lower).find() && whitespaceCount <= 8;
    }

    private List<String> splitIntoSentences(String line) {
        List<String> parts = new ArrayList<>();
        for (String sentence : line.split("(?<=[。！？.!?;；])\\s+")) {
            String trimmed = normalizeWhitespace(sentence);
            if (!trimmed.isBlank()) {
                parts.add(trimmed);
            }
        }
        if (parts.isEmpty()) {
            parts.add(line);
        }
        return parts;
    }

    private String normalizeWhitespace(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").trim();
    }

    private String trim(String text, int maxChars) {
        if (text == null || text.length() <= maxChars) {
            return text;
        }
        return text.substring(0, Math.max(0, maxChars - 1)).trim() + "…";
    }

    private record SentenceCandidate(String section, String text) {
    }
}
