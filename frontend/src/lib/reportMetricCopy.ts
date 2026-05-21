export type ReportMetricLocale = "zh" | "en";

const METRIC_NAME_TRANSLATIONS: Array<{
  pattern: RegExp;
  zh: string;
}> = [
  { pattern: /^(revenue|total revenue)$/i, zh: "营收" },
  { pattern: /^(gross margin)$/i, zh: "毛利率" },
  { pattern: /^(operating income)$/i, zh: "营业利润" },
  { pattern: /^(operating cash flow)$/i, zh: "经营现金流" },
  { pattern: /^(capital expenditures?|capex)$/i, zh: "资本开支" },
  { pattern: /^(free cash flow|fcf)$/i, zh: "自由现金流" },
  { pattern: /^(net income|net profit)$/i, zh: "净利润" },
  { pattern: /^(earnings per share|eps)$/i, zh: "每股收益" },
  { pattern: /^(revenue yoy|revenue growth|year[- ]over[- ]year revenue)$/i, zh: "营收同比" },
  { pattern: /^(cash and cash equivalents)$/i, zh: "现金及现金等价物" },
];

const METRIC_INTERPRETATION_TRANSLATIONS: Array<{
  pattern: RegExp;
  zh: string;
}> = [
  { pattern: /^reported metric\.?$/i, zh: "已披露指标。" },
  { pattern: /^revenue increased\.?$/i, zh: "营收增长。" },
  { pattern: /^margin expanded\.?$/i, zh: "利润率扩张。" },
  { pattern: /^margin compressed\.?$/i, zh: "利润率收窄。" },
  { pattern: /^cash conversion improved\.?$/i, zh: "现金转化改善。" },
  { pattern: /^capex remained disciplined\.?$/i, zh: "资本开支保持克制。" },
  { pattern: /^profitability improved\.?$/i, zh: "盈利能力改善。" },
  { pattern: /^earnings remained resilient\.?$/i, zh: "盈利保持韧性。" },
];

export function formatMetricName(metricName: string, locale: ReportMetricLocale) {
  if (locale !== "zh") {
    return metricName;
  }

  const normalized = metricName.trim();
  const translated = METRIC_NAME_TRANSLATIONS.find(({ pattern }) =>
    pattern.test(normalized),
  );
  return translated?.zh ?? metricName;
}

export function formatMetricInterpretation(
  interpretation: string,
  locale: ReportMetricLocale,
) {
  if (locale !== "zh") {
    return interpretation;
  }

  const normalized = interpretation.trim();
  const translated = METRIC_INTERPRETATION_TRANSLATIONS.find(({ pattern }) =>
    pattern.test(normalized),
  );
  return translated?.zh ?? interpretation;
}
