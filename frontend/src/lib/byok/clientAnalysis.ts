import type {
  AnalysisReport,
  BusinessDriverSections,
  CashFlowCapitalAllocationSections,
  EvidenceBoundMetric,
  EvidenceBoundPoint,
  EvidenceRef,
  LatestEarningsSections,
  ResearchTaskType,
} from "@/types/AnalysisReport";

export type ClientByokProvider = "siliconflow" | "openai" | "gemini";

export type ClientByokAnalysisOptions = {
  ticker: string;
  taskId: ResearchTaskType;
  lang: "zh" | "en";
  provider: ClientByokProvider;
  model: string;
  apiKey: string;
  signal?: AbortSignal;
};

type FinancialFacts = Record<string, unknown>;

type ProviderJsonResponse = {
  choices?: Array<{
    message?: {
      content?: string;
    };
  }>;
  candidates?: Array<{
    content?: {
      parts?: Array<{
        text?: string;
      }>;
    };
  }>;
};

const BYOK_PROVIDER_MAX_TOKENS = 3600;
const BYOK_PROVIDER_JSON_RETRY_MAX_TOKENS = 4200;

export async function runClientByokAnalysis({
  ticker,
  taskId,
  lang,
  provider,
  model,
  apiKey,
  signal,
}: ClientByokAnalysisOptions): Promise<AnalysisReport> {
  const normalizedTicker = ticker.trim().toUpperCase();
  const [facts, filingText] = await Promise.all([
    fetchFinancialFacts(normalizedTicker, signal),
    fetchFilingText(normalizedTicker, signal),
  ]);
  const prompt = buildClientSynthesisPrompt({
    ticker: normalizedTicker,
    taskId,
    lang,
    facts,
    filingText,
  });
  const payload = await completeProviderJson({
    provider,
    model,
    apiKey,
    prompt,
    signal,
  });
  const report = normalizeClientReport(payload, {
    ticker: normalizedTicker,
    taskId,
    lang,
    model,
    provider,
    facts,
  });
  return report;
}

async function fetchFinancialFacts(ticker: string, signal?: AbortSignal) {
  const response = await fetch(`/api/java/financial/${encodeURIComponent(ticker)}`, {
    signal,
  });
  if (!response.ok) {
    return {};
  }
  return (await response.json()) as FinancialFacts;
}

async function fetchFilingText(ticker: string, signal?: AbortSignal) {
  const response = await fetch(`/api/java/sec/10k/${encodeURIComponent(ticker)}`, {
    signal,
  });
  if (!response.ok) {
    return "";
  }
  return (await response.text()).slice(0, 36_000);
}

function buildClientSynthesisPrompt({
  ticker,
  taskId,
  lang,
  facts,
  filingText,
}: {
  ticker: string;
  taskId: ResearchTaskType;
  lang: "zh" | "en";
  facts: FinancialFacts;
  filingText: string;
}) {
  const languageInstruction =
    lang === "zh"
      ? "Write all analyst-facing prose in simplified Chinese. Keep tickers, model names, accounting terms, and source section names in English when they are proper nouns."
      : "Write all analyst-facing prose in English.";
  return [
    "You are Spring Alpha's client-side earnings analyst.",
    "The user's provider API key is only available in this browser. Do not claim that a server-side agent used the key.",
    languageInstruction,
    "Return strict JSON only. Do not include markdown fences.",
    `Ticker: ${ticker}`,
    `Task type: ${taskId}`,
    "Required top-level JSON keys: executiveSummary, companyName, period, filingDate, citations, taskSections.",
    "Use taskSections.schemaVersion = task_sections.v1 and taskSections.taskType equal to the requested task type.",
    "Every point must be evidence-bound. Use concise but specific paragraphs, not generic filler.",
    "If a fact is missing, say it is not disclosed in the supplied evidence rather than inventing it.",
    `Financial facts JSON:\n${JSON.stringify(facts).slice(0, 12_000)}`,
    `Filing excerpt:\n${filingText || "No filing excerpt was available."}`,
    taskSchemaInstruction(taskId),
  ].join("\n\n");
}

function taskSchemaInstruction(taskId: ResearchTaskType) {
  if (taskId === "business_driver_deep_dive") {
    return [
      "For business_driver_deep_dive, taskSections must include:",
      "driverThesis { headline, durability, summary }",
      "driverMap { revenueBridge, segmentMomentum, marginAndMix, demandSignals }",
      "Each driverMap value is either null or { title, summary, evidenceRefs, citationStatus }.",
    ].join("\n");
  }
  if (taskId === "cash_flow_capital_allocation") {
    return [
      "For cash_flow_capital_allocation, taskSections must include:",
      "cashQualityVerdict { headline, earningsBackedByCash, summary }",
      "cashMetrics: array of { name, value, period, interpretation, evidenceRefs, citationStatus }",
      "capitalAllocation { capex, buybacks, dividends, debt, liquidity }",
      "allocationDiscipline and redFlags arrays of evidence-bound points.",
    ].join("\n");
  }
  return [
    "For latest_earnings_readout, taskSections must include:",
    "companyProfile { summary, evidenceRefs, citationStatus }",
    "toplineVerdict { headline, summary, verdict, confidence }",
    "keyTakeaways, driverSnapshot, riskSnapshot arrays of evidence-bound points",
    "financialDashboard { metrics, chartFocus }",
    "driversAndDraggers { drivers, draggers }",
    "bullBearRead { bullCase, bearCase, balancedRead }",
    "watchNext array of { title, metric, whyItMatters, evidenceRefs, citationStatus }.",
  ].join("\n");
}

async function completeProviderJson({
  provider,
  model,
  apiKey,
  prompt,
  signal,
}: {
  provider: ClientByokProvider;
  model: string;
  apiKey: string;
  prompt: string;
  signal?: AbortSignal;
}) {
  if (provider === "gemini") {
    return completeGeminiJson({ model, apiKey, prompt, signal });
  }
  return completeOpenAiCompatibleJson({ provider, model, apiKey, prompt, signal });
}

async function completeOpenAiCompatibleJson({
  provider,
  model,
  apiKey,
  prompt,
  signal,
}: {
  provider: Exclude<ClientByokProvider, "gemini">;
  model: string;
  apiKey: string;
  prompt: string;
  signal?: AbortSignal;
}) {
  const baseUrl =
    provider === "siliconflow"
      ? "https://api.siliconflow.cn/v1"
      : "https://api.openai.com/v1";
  const requestCompletion = async (completionPrompt: string, maxTokens: number) => {
    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: "user",
            content: completionPrompt,
          },
        ],
        response_format: { type: "json_object" },
        temperature: 0.2,
        max_tokens: maxTokens,
      }),
      signal,
    });
    const body = (await response.json().catch(() => ({}))) as ProviderJsonResponse & {
      error?: { message?: string; code?: string };
    };
    if (!response.ok) {
      throw providerError(provider, response.status, body.error?.message);
    }
    return parseJsonObject(body.choices?.[0]?.message?.content ?? "");
  };

  try {
    return await requestCompletion(prompt, BYOK_PROVIDER_MAX_TOKENS);
  } catch (error) {
    if (!isJsonSyntaxError(error)) {
      throw error;
    }
    try {
      return await requestCompletion(
        buildJsonRetryPrompt(prompt),
        BYOK_PROVIDER_JSON_RETRY_MAX_TOKENS,
      );
    } catch (retryError) {
      if (isJsonSyntaxError(retryError)) {
        throw providerJsonError();
      }
      throw retryError;
    }
  }
}

async function completeGeminiJson({
  model,
  apiKey,
  prompt,
  signal,
}: {
  model: string;
  apiKey: string;
  prompt: string;
  signal?: AbortSignal;
}) {
  const requestCompletion = async (completionPrompt: string, maxOutputTokens: number) => {
    const response = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(
        model,
      )}:generateContent`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": apiKey,
        },
        body: JSON.stringify({
          contents: [{ parts: [{ text: completionPrompt }] }],
          generationConfig: {
            responseMimeType: "application/json",
            temperature: 0.2,
            maxOutputTokens,
          },
        }),
        signal,
      },
    );
    const body = (await response.json().catch(() => ({}))) as ProviderJsonResponse & {
      error?: { message?: string; code?: string };
    };
    if (!response.ok) {
      throw providerError("gemini", response.status, body.error?.message);
    }
    return parseJsonObject(body.candidates?.[0]?.content?.parts?.[0]?.text ?? "");
  };

  try {
    return await requestCompletion(prompt, BYOK_PROVIDER_MAX_TOKENS);
  } catch (error) {
    if (!isJsonSyntaxError(error)) {
      throw error;
    }
    try {
      return await requestCompletion(
        buildJsonRetryPrompt(prompt),
        BYOK_PROVIDER_JSON_RETRY_MAX_TOKENS,
      );
    } catch (retryError) {
      if (isJsonSyntaxError(retryError)) {
        throw providerJsonError();
      }
      throw retryError;
    }
  }
}

function parseJsonObject(content: string) {
  const trimmed = content.trim().replace(/^```json\s*/i, "").replace(/```$/i, "");
  if (!trimmed) {
    throw new Error("Provider returned an empty JSON response.");
  }
  return JSON.parse(trimmed) as Record<string, unknown>;
}

function isJsonSyntaxError(error: unknown) {
  return error instanceof SyntaxError;
}

function buildJsonRetryPrompt(prompt: string) {
  return `${prompt}\n\nThe previous response was invalid or truncated JSON. Return a smaller strict JSON object now. Keep summaries concise, cap arrays at 3 items, and do not include markdown fences.`;
}

function providerJsonError() {
  return new Error(
    "Provider returned incomplete JSON twice. Please retry, choose a shorter task, or switch models.",
  );
}

function providerError(provider: ClientByokProvider, status: number, message?: string) {
  const displayName =
    provider === "siliconflow" ? "SiliconFlow" : provider === "openai" ? "OpenAI" : "Gemini";
  return new Error(
    message || `${displayName} API key is invalid or unauthorized for this project (${status}).`,
  );
}

function normalizeClientReport(
  rawReport: Record<string, unknown>,
  context: {
    ticker: string;
    taskId: ResearchTaskType;
    lang: "zh" | "en";
    model: string;
    provider: ClientByokProvider;
    facts: FinancialFacts;
  },
): AnalysisReport {
  const rawTaskSections =
    objectValue(rawReport.taskSections) ?? objectValue(rawReport.task_sections) ?? {};
  const taskSections = normalizeTaskSections(rawTaskSections, context);
  const citations = Array.isArray(rawReport.citations)
    ? (rawReport.citations as AnalysisReport["citations"])
    : evidenceRefsFromTaskSections(taskSections).slice(0, 8).map((ref) => ({
        section: ref.section,
        excerpt: ref.excerpt,
        verificationStatus: "UNVERIFIED" as const,
      }));
  return {
    executiveSummary:
      stringValue(rawReport.executiveSummary) ||
      stringValue(rawReport.executive_summary) ||
      taskSummary(taskSections, context.lang),
    companyName:
      stringValue(rawReport.companyName) ||
      stringValue(rawReport.company_name) ||
      stringValue(context.facts.companyName) ||
      stringValue(context.facts.company_name) ||
      context.ticker,
    period:
      stringValue(rawReport.period) ||
      stringValue(context.facts.period) ||
      undefined,
    filingDate:
      stringValue(rawReport.filingDate) ||
      stringValue(rawReport.filing_date) ||
      stringValue(context.facts.filingDate) ||
      stringValue(context.facts.filing_date) ||
      undefined,
    reportType: "quarterly",
    keyMetrics: [],
    businessDrivers: [],
    riskFactors: [],
    bullCase: "",
    bearCase: "",
    citations,
    metadata: {
      modelName: `${context.provider}:${context.model}`,
      generatedAt: new Date().toISOString(),
      language: context.lang,
      agentEvents: [
        {
          phase: "draft_report_sections",
          status: "ok",
          summary:
            "Browser-direct BYOK synthesis completed without sending the provider key to Spring Alpha servers.",
          eventKind: "reasoning",
          agentName: "Client BYOK Analyst",
          modelName: context.model,
          latencyMs: 0,
        },
      ],
    },
    sourceContext: {
      status: "GROUNDED",
      message:
        context.lang === "zh"
          ? "用户 Key 仅在浏览器中用于直连 provider；Spring Alpha 服务端没有接收该 Key。"
          : "The user key was used only in the browser-direct provider call; Spring Alpha servers did not receive it.",
    },
    taskSections,
  };
}

function normalizeTaskSections(
  rawTaskSections: Record<string, unknown>,
  context: {
    taskId: ResearchTaskType;
    lang: "zh" | "en";
    facts: FinancialFacts;
  },
): NonNullable<AnalysisReport["taskSections"]> {
  const coverage = {
    status: "complete" as const,
    missingSections: [],
    evidenceCount: evidenceRefsFromUnknown(rawTaskSections).length,
    ...objectValue(rawTaskSections.coverage),
  };
  if (context.taskId === "business_driver_deep_dive") {
    const section = normalizeBusinessDriverSections(rawTaskSections, coverage, context);
    return {
      schemaVersion: "task_sections.v1",
      taskType: context.taskId,
      coverage,
      businessDriver: section,
    };
  }
  if (context.taskId === "cash_flow_capital_allocation") {
    const section = normalizeCashFlowSections(rawTaskSections, coverage, context);
    return {
      schemaVersion: "task_sections.v1",
      taskType: context.taskId,
      coverage,
      cashFlowCapitalAllocation: section,
    };
  }
  const section = normalizeLatestEarningsSections(rawTaskSections, coverage, context);
  return {
    schemaVersion: "task_sections.v1",
    taskType: context.taskId,
    coverage,
    latestEarnings: section,
  };
}

function normalizeLatestEarningsSections(
  raw: Record<string, unknown>,
  coverage: LatestEarningsSections["coverage"],
  context: { lang: "zh" | "en"; facts: FinancialFacts },
): LatestEarningsSections {
  const latest = objectValue(raw.latestEarnings) ?? raw;
  return {
    schemaVersion: "task_sections.v1",
    taskType: "latest_earnings_readout",
    coverage,
    companyProfile: objectValue(latest.companyProfile)
      ? (latest.companyProfile as LatestEarningsSections["companyProfile"])
      : {
          summary:
            stringValue(context.facts.marketBusinessSummary) ||
            stringValue(context.facts.businessSummary) ||
            fallbackText(context.lang, "Company profile evidence was limited."),
          evidenceRefs: defaultEvidenceRefs(),
          citationStatus: "partial",
        },
    toplineVerdict: {
      headline:
        stringValue(objectValue(latest.toplineVerdict)?.headline) ||
        fallbackText(context.lang, "Latest earnings thesis"),
      summary:
        stringValue(objectValue(latest.toplineVerdict)?.summary) ||
        fallbackText(context.lang, "The supplied facts support a mixed earnings readout."),
      verdict:
        enumValue(objectValue(latest.toplineVerdict)?.verdict, [
          "positive",
          "mixed",
          "negative",
        ] as const) ??
        "mixed",
      confidence:
        enumValue(objectValue(latest.toplineVerdict)?.confidence, [
          "high",
          "medium",
          "low",
        ] as const) ??
        "medium",
    },
    keyTakeaways: pointArray(latest.keyTakeaways),
    financialDashboard: {
      metrics: metricArray(objectValue(latest.financialDashboard)?.metrics),
      chartFocus: stringArray(objectValue(latest.financialDashboard)?.chartFocus),
    },
    driverSnapshot: pointArray(latest.driverSnapshot),
    riskSnapshot: pointArray(latest.riskSnapshot),
    driversAndDraggers: objectValue(latest.driversAndDraggers)
      ? (latest.driversAndDraggers as LatestEarningsSections["driversAndDraggers"])
      : { drivers: [], draggers: [] },
    bullBearRead: objectValue(latest.bullBearRead)
      ? (latest.bullBearRead as LatestEarningsSections["bullBearRead"])
      : { bullCase: [], bearCase: [] },
    watchNext: Array.isArray(latest.watchNext)
      ? (latest.watchNext as LatestEarningsSections["watchNext"])
      : [],
  };
}

function normalizeBusinessDriverSections(
  raw: Record<string, unknown>,
  coverage: BusinessDriverSections["coverage"],
  context: { lang: "zh" | "en" },
): BusinessDriverSections {
  const business = objectValue(raw.businessDriver) ?? raw;
  return {
    schemaVersion: "task_sections.v1",
    taskType: "business_driver_deep_dive",
    coverage,
    driverThesis: {
      headline:
        stringValue(objectValue(business.driverThesis)?.headline) ||
        fallbackText(context.lang, "Business driver thesis"),
      durability:
        enumValue(objectValue(business.driverThesis)?.durability, [
          "durable",
          "mixed",
          "temporary",
          "unclear",
        ] as const) ?? "mixed",
      summary:
        stringValue(objectValue(business.driverThesis)?.summary) ||
        fallbackText(context.lang, "The available evidence suggests mixed driver durability."),
    },
    driverMap: {
      revenueBridge: pointOrNull(objectValue(business.driverMap)?.revenueBridge),
      segmentMomentum: pointOrNull(objectValue(business.driverMap)?.segmentMomentum),
      marginAndMix: pointOrNull(objectValue(business.driverMap)?.marginAndMix),
      demandSignals: pointOrNull(objectValue(business.driverMap)?.demandSignals),
    },
  };
}

function normalizeCashFlowSections(
  raw: Record<string, unknown>,
  coverage: CashFlowCapitalAllocationSections["coverage"],
  context: { lang: "zh" | "en" },
): CashFlowCapitalAllocationSections {
  const cash = objectValue(raw.cashFlowCapitalAllocation) ?? raw;
  const allocation = objectValue(cash.capitalAllocation) ?? {};
  return {
    schemaVersion: "task_sections.v1",
    taskType: "cash_flow_capital_allocation",
    coverage,
    cashQualityVerdict: {
      headline:
        stringValue(objectValue(cash.cashQualityVerdict)?.headline) ||
        fallbackText(context.lang, "Cash quality verdict"),
      earningsBackedByCash:
        enumValue(objectValue(cash.cashQualityVerdict)?.earningsBackedByCash, [
          "yes",
          "mixed",
          "no",
          "unclear",
        ] as const) ?? "mixed",
      summary:
        stringValue(objectValue(cash.cashQualityVerdict)?.summary) ||
        fallbackText(context.lang, "Cash conversion evidence was mixed."),
    },
    cashMetrics: metricArray(cash.cashMetrics),
    capitalAllocation: {
      capex: pointArray(allocation.capex),
      buybacks: pointArray(allocation.buybacks),
      dividends: pointArray(allocation.dividends),
      debt: pointArray(allocation.debt),
      liquidity: pointArray(allocation.liquidity),
    },
    allocationDiscipline: pointArray(cash.allocationDiscipline),
    redFlags: pointArray(cash.redFlags),
  };
}

function pointArray(value: unknown): EvidenceBoundPoint[] {
  return Array.isArray(value) ? value.map(pointValue).filter(Boolean) : [];
}

function pointOrNull(value: unknown): EvidenceBoundPoint | null {
  return value ? pointValue(value) : null;
}

function pointValue(value: unknown): EvidenceBoundPoint {
  const object = objectValue(value) ?? {};
  return {
    title: stringValue(object.title) || "Evidence point",
    summary: stringValue(object.summary) || stringValue(object.description) || "Evidence was limited.",
    evidenceRefs: evidenceRefsFromUnknown(object.evidenceRefs),
    citationStatus:
      enumValue(object.citationStatus, [
        "supported",
        "partial",
        "missing",
        "unverified",
      ] as const) ??
      "partial",
  };
}

function metricArray(value: unknown): EvidenceBoundMetric[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.reduce<EvidenceBoundMetric[]>((metrics, item) => {
    const object = objectValue(item);
    if (!object) {
      return metrics;
    }
    metrics.push({
      name: stringValue(object.name) || "Metric",
      value: stringValue(object.value) || "Not disclosed",
      period: stringValue(object.period) || undefined,
      interpretation:
        stringValue(object.interpretation) ||
        stringValue(object.summary) ||
        "Reported metric.",
      evidenceRefs: evidenceRefsFromUnknown(object.evidenceRefs),
      citationStatus:
        enumValue(object.citationStatus, [
          "supported",
          "partial",
          "missing",
          "unverified",
        ] as const) ?? "partial",
    });
    return metrics;
  }, []);
}

function evidenceRefsFromUnknown(value: unknown): EvidenceRef[] {
  if (!Array.isArray(value)) return defaultEvidenceRefs();
  const refs = value.reduce<EvidenceRef[]>((items, item) => {
    const object = objectValue(item);
    if (!object) {
      return items;
    }
    const ref: EvidenceRef = {
      section: stringValue(object.section) || "Supplied evidence",
      excerpt:
        stringValue(object.excerpt) ||
        stringValue(object.snippet) ||
        "Evidence excerpt was not quoted by the model.",
    };
    const filingDate = stringValue(object.filingDate) || stringValue(object.filing_date);
    if (filingDate) {
      ref.filingDate = filingDate;
    }
    const accessionNumber =
      stringValue(object.accessionNumber) || stringValue(object.accession_number);
    if (accessionNumber) {
      ref.accessionNumber = accessionNumber;
    }
    const sourceId = stringValue(object.sourceId) || stringValue(object.source_id);
    if (sourceId) {
      ref.sourceId = sourceId;
    }
    items.push(ref);
    return items;
  }, []);
  return refs.length > 0 ? refs : defaultEvidenceRefs();
}

function evidenceRefsFromTaskSections(
  taskSections: NonNullable<AnalysisReport["taskSections"]>,
) {
  const refs: EvidenceRef[] = [];
  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    const object = objectValue(value);
    if (!object) {
      return;
    }
    const evidenceRefs = object.evidenceRefs;
    if (Array.isArray(evidenceRefs)) {
      refs.push(...evidenceRefsFromUnknown(evidenceRefs));
    }
    Object.values(object).forEach(visit);
  };
  visit(taskSections);
  return refs.length > 0 ? refs : defaultEvidenceRefs();
}

function defaultEvidenceRefs(): EvidenceRef[] {
  return [
    {
      section: "Supplied evidence",
      excerpt: "Generated from browser-fetched financial facts and filing excerpts.",
    },
  ];
}

function taskSummary(
  taskSections: NonNullable<AnalysisReport["taskSections"]>,
  lang: "zh" | "en",
) {
  if ("latestEarnings" in taskSections && taskSections.latestEarnings) {
    return taskSections.latestEarnings.toplineVerdict.summary;
  }
  if ("businessDriver" in taskSections && taskSections.businessDriver) {
    return taskSections.businessDriver.driverThesis.summary;
  }
  if ("cashFlowCapitalAllocation" in taskSections && taskSections.cashFlowCapitalAllocation) {
    return taskSections.cashFlowCapitalAllocation.cashQualityVerdict.summary;
  }
  return fallbackText(lang, "Client-side BYOK analysis completed.");
}

function fallbackText(lang: "zh" | "en", text: string) {
  if (lang === "en") return text;
  const zhFallbacks: Record<string, string> = {
    "Company profile evidence was limited.": "公司画像证据有限。",
    "Latest earnings thesis": "最新财报观点",
    "The supplied facts support a mixed earnings readout.": "已提供事实支持一个分化的财报判断。",
    "Business driver thesis": "业务驱动观点",
    "The available evidence suggests mixed driver durability.": "现有证据显示业务驱动的持续性较为分化。",
    "Cash quality verdict": "现金质量判断",
    "Cash conversion evidence was mixed.": "现金转化证据较为分化。",
    "Client-side BYOK analysis completed.": "浏览器端 BYOK 分析已完成。",
  };
  return zhFallbacks[text] ?? text;
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function enumValue<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return typeof value === "string" && allowed.includes(value as T)
    ? (value as T)
    : null;
}
