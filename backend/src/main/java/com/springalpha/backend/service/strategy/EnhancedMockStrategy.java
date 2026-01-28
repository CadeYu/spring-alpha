package com.springalpha.backend.service.strategy;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * Enhanced Mock Strategy - Returns structured AnalysisReport for testing.
 * This demonstrates the expected output format for all AI strategies.
 */
@Service
public class EnhancedMockStrategy implements AiAnalysisStrategy {

    private static final Logger log = LoggerFactory.getLogger(EnhancedMockStrategy.class);

    @Override
    public String getName() {
        return "enhanced-mock";
    }

    @Override
    public Flux<AnalysisReport> analyze(AnalysisContract contract) {
        log.info("🎭 Enhanced Mock Strategy analyzing: {} ({})",
                contract.getTicker(), contract.getPeriod());

        // Build structured report based on financial facts
        AnalysisReport report = buildMockReport(contract);

        // Return as single emission (real LLMs would stream partial reports)
        return Flux.just(report);
    }

    private AnalysisReport buildMockReport(AnalysisContract contract) {
        String ticker = contract.getTicker();
        String lang = contract.getLanguage();

        // Build metric insights
        List<AnalysisReport.MetricInsight> metrics = new ArrayList<>();

        if (contract.getFinancialFacts().getRevenueYoY() != null) {
            double yoyPercent = contract.getFinancialFacts().getRevenueYoY().doubleValue() * 100;
            metrics.add(AnalysisReport.MetricInsight.builder()
                    .metricName("Revenue YoY Growth")
                    .value(String.format("%.2f%%", yoyPercent))
                    .interpretation(yoyPercent > 5
                            ? "Strong revenue growth indicates healthy business expansion"
                            : "Revenue growth is below industry average")
                    .sentiment(yoyPercent > 5 ? "positive" : "neutral")
                    .build());
        }

        if (contract.getFinancialFacts().getGrossMargin() != null) {
            double margin = contract.getFinancialFacts().getGrossMargin().doubleValue() * 100;
            metrics.add(AnalysisReport.MetricInsight.builder()
                    .metricName("Gross Margin")
                    .value(String.format("%.2f%%", margin))
                    .interpretation(margin > 40
                            ? "High gross margin shows strong pricing power"
                            : "Gross margin is under pressure")
                    .sentiment(margin > 40 ? "positive" : "negative")
                    .build());
        }

        // Build business drivers
        List<AnalysisReport.BusinessDriver> drivers = new ArrayList<>();
        drivers.add(AnalysisReport.BusinessDriver.builder()
                .title("Product Innovation")
                .description("New product launches driving revenue growth")
                .impact("high")
                .build());

        // Build risk factors
        List<AnalysisReport.RiskFactor> risks = new ArrayList<>();
        risks.add(AnalysisReport.RiskFactor.builder()
                .category("Market Risk")
                .description("Increasing competition in core markets")
                .severity("medium")
                .build());

        // Build citations
        List<AnalysisReport.Citation> citations = new ArrayList<>();
        if (contract.getTextEvidence() != null && contract.getTextEvidence().containsKey("MD&A")) {
            citations.add(AnalysisReport.Citation.builder()
                    .section("MD&A")
                    .excerpt("Revenue increased due to strong product demand...")
                    .build());
        }

        // Build metadata
        AnalysisReport.AnalysisMetadata metadata = AnalysisReport.AnalysisMetadata.builder()
                .modelName("enhanced-mock-v1")
                .generatedAt(Instant.now().toString())
                .language(lang != null ? lang : "en")
                .build();

        return AnalysisReport.builder()
                .executiveSummary(String.format(
                        "%s reported solid performance in %s with revenue growth of %.2f%% YoY",
                        ticker,
                        contract.getPeriod(),
                        contract.getFinancialFacts().getRevenueYoY() != null
                                ? contract.getFinancialFacts().getRevenueYoY().doubleValue() * 100
                                : 0.0))
                .keyMetrics(metrics)
                .businessDrivers(drivers)
                .riskFactors(risks)
                .bullCase("Strong fundamentals and market position support continued growth")
                .bearCase("Valuation appears stretched; macro headwinds may impact near-term performance")
                .citations(citations)
                .metadata(metadata)
                .build();
    }
}
