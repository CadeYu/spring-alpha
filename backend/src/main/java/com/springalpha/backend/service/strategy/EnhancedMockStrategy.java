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
  protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
    log.info("🎭 Enhanced Mock Strategy - simulating LLM response");

    // Detect which agent is calling based on prompt content
    String mockJsonResponse;
    if (userPrompt.contains("Core Thesis") || userPrompt.contains("Bull/Bear Case")
        || userPrompt.contains("Executive Summary")) {
      mockJsonResponse = generateSummaryMock(lang);
    } else if (userPrompt.contains("DuPont Analysis")) {
      mockJsonResponse = generateInsightsMock(lang);
    } else if (userPrompt.contains("factor bridges") || userPrompt.contains("Topic Trend")) {
      mockJsonResponse = generateFactorsMock(lang);
    } else if (userPrompt.contains("Business Drivers") || userPrompt.contains("Risk Factors")) {
      mockJsonResponse = generateDriversMock(lang);
    } else {
      mockJsonResponse = generateSummaryMock(lang);
    }

    return Flux.just(mockJsonResponse);
  }

  private String generateSummaryMock(String lang) {
    boolean zh = "zh".equalsIgnoreCase(lang);
    return String.format(
        """
            {
              "coreThesis": {
                "verdict": "%s",
                "headline": "%s",
                "summary": "%s",
                "keyPoints": ["%s", "%s", "%s"],
                "supportingEvidence": [
                  {"label": "%s", "detail": "%s"},
                  {"label": "%s", "detail": "%s"}
                ],
                "watchItems": ["%s", "%s"]
              },
              "executiveSummary": "%s",
              "keyMetrics": [
                {"metricName": "%s", "value": "6.07%%", "interpretation": "%s", "sentiment": "positive"},
                {"metricName": "%s", "value": "44.13%%", "interpretation": "%s", "sentiment": "positive"}
              ],
              "bullCase": "%s",
              "bearCase": "%s",
              "citations": [{"section": "MD&A", "excerpt": "Revenue growth primarily driven by strong performance in core product lines"}]
            }
            """,
        zh ? "positive" : "positive",
        zh ? "营收与利润率协同改善，基本面韧性强于市场预期"
            : "Revenue resilience and margin discipline are reinforcing the equity story",
        zh ? "公司本期不仅维持了稳健的营收表现，还通过毛利率改善和经营效率优化强化了盈利质量，说明增长并非单纯依赖短期促销，而是来自更健康的业务组合与执行力。"
            : "The company paired resilient top-line execution with improving margin quality, suggesting the quarter was driven by healthier mix and operating discipline rather than purely short-term demand pull-forward.",
        zh ? "营收表现稳健，显示核心需求未明显走弱"
            : "Revenue remained resilient, indicating core demand has not meaningfully deteriorated",
        zh ? "毛利率抬升意味着产品组合或执行效率在改善"
            : "Gross margin expansion points to better mix or stronger execution",
        zh ? "盈利能力改善增强了后续再投资与估值支撑"
            : "Improving profitability strengthens reinvestment capacity and valuation support",
        zh ? "增长质量" : "Growth Quality",
        zh ? "营收同比增长与高毛利率同时出现，表明增长质量高于单纯规模扩张。"
            : "Revenue growth accompanied by strong margin structure indicates higher-quality growth than pure volume expansion.",
        zh ? "经营杠杆" : "Operating Leverage",
        zh ? "收入增长转化为更好的利润表现，说明成本控制与经营杠杆开始释放。"
            : "Revenue gains are translating into better profit outcomes, indicating cost control and operating leverage are starting to show through.",
        zh ? "后续需观察增长是否延续，以及利润率改善能否在竞争加剧环境下保持。"
            : "Watch whether growth remains durable and if margin gains hold under a more competitive backdrop.",
        zh ? "若宏观环境转弱，高估值对短期波动会更敏感。"
            : "A weaker macro backdrop could make the current valuation more sensitive to near-term volatility.",
        zh ? "公司本期业绩稳健，营收同比增长显著，毛利率保持高位"
            : "Company delivered solid performance with notable YoY revenue growth and strong gross margin",
        zh ? "营收同比增长" : "Revenue YoY Growth",
        zh ? "稳健的营收增长显示业务扩张势头良好" : "Solid revenue growth indicates healthy business expansion",
        zh ? "毛利率" : "Gross Margin",
        zh ? "高毛利率展现了强大的定价能力" : "High gross margin demonstrates strong pricing power",
        zh ? "强劲基本面支撑持续增长" : "Strong fundamentals support continued growth",
        zh ? "估值偏高；宏观逆风可能影响短期表现" : "Valuation stretched; macro headwinds may impact near-term");
  }

  private String generateInsightsMock(String lang) {
    boolean zh = "zh".equalsIgnoreCase(lang);
    return String.format("""
        {
          "dupontAnalysis": {
            "netProfitMargin": "34.2%%",
            "assetTurnover": "0.52x",
            "equityMultiplier": "1.45x",
            "returnOnEquity": "25.8%%",
            "interpretation": "%s"
          },
          "insightEngine": {
            "accountingChanges": [
              {"policyName": "%s", "changeDescription": "%s", "riskAssessment": "low"}
            ],
            "rootCauseAnalysis": [
              {"metric": "%s", "reason": "%s", "evidence": "Based on segment analysis"},
              {"metric": "%s", "reason": "%s", "evidence": "From operational data"}
            ]
          },
          "citations": [{"section": "MD&A", "excerpt": "Return on equity driven by strong net profit margins"}]
        }
        """,
        zh ? "ROE 由高净利润率驱动，资产周转效率稳定" : "ROE is primarily driven by high net profit margins with stable asset turnover",
        zh ? "收入确认" : "Revenue Recognition",
        zh ? "采用新收入确认准则，影响较小" : "Adopted new revenue recognition standard with minimal impact",
        zh ? "毛利率" : "Gross Margin",
        zh ? "产品组合优化和运营效率提升" : "Product mix optimization and operational efficiency improvements",
        zh ? "营收增长" : "Revenue Growth",
        zh ? "广告业务强劲增长推动整体营收上升" : "Strong ad business growth driving overall revenue increase");
  }

  private String generateFactorsMock(String lang) {
    boolean zh = "zh".equalsIgnoreCase(lang);
    return String.format("""
        {
          "factorAnalysis": {
            "revenueBridge": [
              {"name": "%s", "impact": "+12%%", "description": "%s"},
              {"name": "%s", "impact": "+8%%", "description": "%s"},
              {"name": "%s", "impact": "-2%%", "description": "%s"}
            ],
            "marginBridge": [
              {"name": "%s", "impact": "+3%%", "description": "%s"},
              {"name": "%s", "impact": "-1%%", "description": "%s"}
            ]
          },
          "topicTrends": [
            {"topic": "AI", "frequency": 92, "sentiment": "positive"},
            {"topic": "%s", "frequency": 78, "sentiment": "positive"},
            {"topic": "%s", "frequency": 65, "sentiment": "neutral"},
            {"topic": "%s", "frequency": 55, "sentiment": "positive"},
            {"topic": "%s", "frequency": 45, "sentiment": "negative"}
          ],
          "citations": [{"section": "MD&A", "excerpt": "Revenue growth driven by advertising volume increases"}]
        }
        """,
        zh ? "广告量增长" : "Ad Volume Growth", zh ? "广告展示量持续上升" : "Increased ad impressions across platforms",
        zh ? "用户增长" : "User Growth", zh ? "日活用户同比增长" : "DAU growth year-over-year",
        zh ? "汇率影响" : "FX Impact", zh ? "强势美元对海外收入不利" : "Strong USD headwind on international revenue",
        zh ? "AI 基础设施" : "AI Infrastructure", zh ? "AI 投资推动效率提升" : "AI investments driving efficiency gains",
        zh ? "运营优化" : "Operational Efficiency", zh ? "人员精简降低运营成本" : "Workforce optimization reducing opex",
        zh ? "元宇宙" : "Metaverse", zh ? "虚拟现实" : "VR/AR",
        zh ? "数字广告" : "Digital Advertising", zh ? "监管合规" : "Regulatory Compliance");
  }

  private String generateDriversMock(String lang) {
    boolean zh = "zh".equalsIgnoreCase(lang);
    return String.format(
        """
            {
              "businessDrivers": [
                {"title": "%s", "description": "%s", "impact": "high"},
                {"title": "%s", "description": "%s", "impact": "high"},
                {"title": "%s", "description": "%s", "impact": "medium"}
              ],
              "riskFactors": [
                {"category": "%s", "description": "%s", "severity": "high"},
                {"category": "%s", "description": "%s", "severity": "medium"},
                {"category": "%s", "description": "%s", "severity": "medium"}
              ],
              "citations": [{"section": "Risk Factors", "excerpt": "Competition in digital advertising market continues to intensify"}]
            }
            """,
        zh ? "AI 广告优化" : "AI-Powered Ad Optimization",
        zh ? "机器学习算法提升广告投放精准度" : "ML algorithms improving ad targeting precision and ROI",
        zh ? "用户增长与参与度" : "User Growth & Engagement",
        zh ? "全球用户基数持续扩大" : "Global user base continues to expand across platforms",
        zh ? "元宇宙投资" : "Metaverse Investment",
        zh ? "Reality Labs 持续投入推动长期增长" : "Reality Labs investment driving long-term growth potential",
        zh ? "监管风险" : "Regulatory Risk",
        zh ? "全球隐私法规趋严可能影响广告业务" : "Increasing global privacy regulations may impact ad targeting capabilities",
        zh ? "竞争风险" : "Competition Risk",
        zh ? "TikTok 等平台的竞争加剧" : "Intensifying competition from TikTok and other platforms",
        zh ? "宏观经济风险" : "Macro Economic Risk",
        zh ? "经济放缓可能减少广告主预算" : "Economic slowdown may reduce advertiser budgets");
  }
}
