package com.springalpha.backend.financial.contract;

import java.util.List;

public record ResearchTaskProfile(
        String primaryEvidenceSection,
        String primaryEvidenceQuery,
        String riskEvidenceQuery,
        List<String> analysisTasks) {

    public static ResearchTaskProfile forTaskType(ResearchTaskType taskType) {
        ResearchTaskType effectiveTaskType = taskType == null
                ? ResearchTaskType.LATEST_EARNINGS_READOUT
                : taskType;

        if (effectiveTaskType == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE) {
            return new ResearchTaskProfile(
                    "Business Drivers",
                    "Management Discussion Analysis products segments demand pricing customers strategy business model customer adoption product services",
                    "Risk Factors competition strategy customer concentration execution risk demand pricing",
                    List.of(
                            "Analyze products, segments, demand, pricing, customers, and strategy actions",
                            "Assess pricing power, customer concentration, competition, and execution risks",
                            "Separate company-specific drivers from generic market commentary"));
        }

        if (effectiveTaskType == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION) {
            return new ResearchTaskProfile(
                    "Cash Flow and Capital Allocation",
                    "Management Discussion Analysis cash flow operating cash flow free cash flow capex capital expenditures buybacks dividends debt liquidity capital allocation",
                    "Risk Factors liquidity capital resources debt obligations financing buybacks dividends capital allocation risk",
                    List.of(
                            "Analyze operating cash flow, free cash flow, capex, buybacks, dividends, debt, and liquidity",
                            "Assess cash conversion quality and capital allocation discipline",
                            "Separate recurring cash generation from one-time financing or working-capital effects"));
        }

        return new ResearchTaskProfile(
                "MD&A",
                "Management Discussion Analysis revenue drivers business performance growth",
                "Risk Factors uncertainties challenges regulatory competition",
                List.of(
                        "Explain the primary drivers of revenue growth",
                        "Analyze the sustainability of margin changes",
                        "Summarize the most material risk factors"));
    }
}
