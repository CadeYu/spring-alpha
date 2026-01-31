package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

/**
 * Enhanced Mock Strategy - Returns structured AnalysisReport for testing.
 * Now extends BaseAiStrategy to use the unified infrastructure.
 */
@Service
public class EnhancedMockStrategy extends BaseAiStrategy {

        private static final Logger log = LoggerFactory.getLogger(EnhancedMockStrategy.class);

        public EnhancedMockStrategy(
                        PromptTemplateService promptService,
                        AnalysisReportValidator validator,
                        ObjectMapper objectMapper) {
                super(promptService, validator, objectMapper);
        }

        @Override
        public String getName() {
                return "enhanced-mock";
        }

        @Override
        protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang) {
                log.info("🎭 Enhanced Mock Strategy - simulating LLM response");

                // In a real strategy, we would call the actual LLM API here
                // For mock, we'll generate a fake JSON response based on the prompt

                // Simulate streaming by emitting the JSON string
                String mockJsonResponse = generateMockJsonResponse(lang);

                return Flux.just(mockJsonResponse);
        }

        /**
         * Generate a mock JSON response that matches AnalysisReport schema
         */
        private String generateMockJsonResponse(String lang) {
                boolean isChinese = "zh".equalsIgnoreCase(lang);

                return String.format("""
                                {
                                  "executiveSummary": "%s",
                                  "keyMetrics": [
                                    {
                                      "metricName": "%s",
                                      "value": "6.07%%",
                                      "interpretation": "%s",
                                      "sentiment": "positive"
                                    },
                                    {
                                      "metricName": "%s",
                                      "value": "44.13%%",
                                      "interpretation": "%s",
                                      "sentiment": "positive"
                                    }
                                  ],
                                  "businessDrivers": [
                                    {
                                      "title": "%s",
                                      "description": "%s",
                                      "impact": "high"
                                    }
                                  ],
                                  "riskFactors": [
                                    {
                                      "category": "%s",
                                      "description": "%s",
                                      "severity": "medium"
                                    }
                                  ],
                                  "bullCase": "%s",
                                  "bearCase": "%s",
                                  "citations": [
                                    {
                                      "section": "MD&A",
                                      "excerpt": "%s"
                                    }
                                  ]
                                }
                                """,
                                isChinese ? "公司本期业绩稳健，营收同比增长6.07%，毛利率保持在44.13%的高位"
                                                : "Company delivered solid performance with 6.07%% YoY revenue growth and maintained strong gross margin of 44.13%%",
                                isChinese ? "营收同比增长" : "Revenue YoY Growth",
                                isChinese ? "稳健的营收增长显示业务扩张势头良好"
                                                : "Solid revenue growth indicates healthy business expansion",
                                isChinese ? "毛利率" : "Gross Margin",
                                isChinese ? "高毛利率展现了强大的定价能力和运营效率"
                                                : "High gross margin demonstrates strong pricing power and operational efficiency",
                                isChinese ? "产品创新" : "Product Innovation",
                                isChinese ? "新产品发布推动了核心业务增长" : "New product launches driving core business growth",
                                isChinese ? "市场风险" : "Market Risk",
                                isChinese ? "核心市场竞争加剧可能影响市场份额"
                                                : "Increasing competition in core markets may impact market share",
                                isChinese ? "强劲的基本面和市场地位支撑持续增长"
                                                : "Strong fundamentals and market position support continued growth",
                                isChinese ? "估值偏高；宏观逆风可能影响短期表现"
                                                : "Valuation appears stretched; macro headwinds may impact near-term performance",
                                isChinese ? "营收增长主要来自核心产品线的稳健表现"
                                                : "Revenue growth primarily driven by strong performance in core product lines");
        }
}
