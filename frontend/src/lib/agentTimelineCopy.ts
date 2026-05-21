export type TimelineLocale = "zh" | "en";

const AGENT_NAME_TRANSLATIONS: Record<string, string> = {
  "Earnings agent": "财报分析师",
  "Earnings Analyst": "财报分析师",
  "Business driver agent": "业务分析师",
  "Business Analyst": "业务分析师",
  "Cash flow agent": "现金流分析师",
  "Cash Flow Analyst": "现金流分析师",
  "Research Agent": "研究智能体",
  "The analyst": "分析师",
};

const BODY_TRANSLATIONS: Array<{ pattern: RegExp; text: string }> = [
  {
    pattern: /^selected the required evidence tools\.$/i,
    text: "已选择 required evidence tools。",
  },
  {
    pattern: /^planned the next evidence step\.$/i,
    text: "已规划下一步证据采集。",
  },
  {
    pattern: /^synthesized the final report sections\.$/i,
    text: "已完成最终报告部分合成。",
  },
  {
    pattern: /^Collected company facts for business drivers\.$/i,
    text: "已收集 business drivers 的 company facts。",
  },
  {
    pattern: /^Searched filing sections for business drivers\.$/i,
    text: "已搜索 business drivers 的 filing sections。",
  },
  {
    pattern: /^Searched metric evidence for business drivers\.$/i,
    text: "已搜索 business drivers 的 metric evidence。",
  },
  {
    pattern: /^Extracted business driver signals\.$/i,
    text: "已提取 business driver signals。",
  },
  {
    pattern: /^Built SEC filing evidence pack for latest earnings\.$/i,
    text: "已构建 latest earnings 的 SEC filing evidence pack。",
  },
  {
    pattern: /^Built SEC filing evidence pack for business drivers\.$/i,
    text: "已构建 business drivers 的 SEC filing evidence pack。",
  },
  {
    pattern: /^Built SEC filing evidence pack for cash flow\.$/i,
    text: "已构建 cash flow 的 SEC filing evidence pack。",
  },
  {
    pattern: /^Agent completed\.$/i,
    text: "Agent 已完成。",
  },
];

export function timelineSectionTitle(locale: TimelineLocale) {
  return locale === "zh" ? "消息与工具" : "Messages & Tools";
}

export function timelineEmptyState(locale: TimelineLocale) {
  return locale === "zh"
    ? "运行完成后，这里会展示 reasoning 与 tool 调用时间线。"
    : "Reasoning and tool-call timeline appears here after an agent finishes.";
}

export function timelineEventKindLabel(kind: "tool" | "reasoning", locale: TimelineLocale) {
  if (kind === "tool") {
    return locale === "zh" ? "工具" : "Tool";
  }
  return locale === "zh" ? "推理" : "Reasoning";
}

export function translateTimelineAgentName(
  agentName: string | null | undefined,
  locale: TimelineLocale,
) {
  if (!agentName) {
    return "";
  }
  if (locale !== "zh") {
    return agentName;
  }
  return AGENT_NAME_TRANSLATIONS[agentName] ?? agentName;
}

export function formatTimelineTokenUsage(
  modelName: string,
  inputTokens: number | null,
  outputTokens: number | null,
  locale: TimelineLocale,
) {
  if (inputTokens !== null || outputTokens !== null) {
    return locale === "zh"
      ? `${modelName}: ${inputTokens ?? "?"} 输入，${outputTokens ?? "?"} 输出`
      : `${modelName}: ${inputTokens ?? "?"} in, ${outputTokens ?? "?"} out`;
  }
  return null;
}

export function translateTimelineSummary(summary: string, locale: TimelineLocale) {
  if (locale !== "zh") {
    return summary;
  }

  const normalized = summary.trim();
  const translatedBodyOnly = translateSummaryBody(normalized);
  if (translatedBodyOnly) {
    return translatedBodyOnly;
  }

  const knownPrefixMatch = matchKnownPrefix(normalized);
  if (knownPrefixMatch) {
    const translatedBody = translateSummaryBody(knownPrefixMatch.body);
    if (translatedBody) {
      return `${knownPrefixMatch.prefix}：${translatedBody}`;
    }
    return `${knownPrefixMatch.prefix}：${knownPrefixMatch.body}`;
  }

  return normalized;
}

function matchKnownPrefix(summary: string):
  | {
      prefix: string;
      body: string;
    }
  | undefined {
  for (const [prefix, translatedPrefix] of Object.entries(AGENT_NAME_TRANSLATIONS)) {
    const needle = `${prefix} `;
    if (summary.startsWith(needle)) {
      return {
        prefix: translatedPrefix,
        body: summary.slice(needle.length),
      };
    }
  }
  return undefined;
}

function translateSummaryBody(body: string) {
  const normalized = body.trim();
  return BODY_TRANSLATIONS.find(({ pattern }) => pattern.test(normalized))?.text;
}
