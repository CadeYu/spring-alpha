export type RagEvalLocale = "zh" | "en";

export type RagEvalMetricKey =
  | "evidenceRetrieved"
  | "evidenceUsed"
  | "metricFacts"
  | "sectionsCovered"
  | "retrievalLatency"
  | "emptyRetrieval"
  | "evidencePackSize";

export type RagEvalMetricTone = "strong" | "stable" | "caution" | "muted";

export interface RagEvalMetricCopy {
  key: RagEvalMetricKey;
  label: string;
  detail: string;
  tone: RagEvalMetricTone;
}

const DASHBOARD_COPY: Record<
  RagEvalLocale,
  {
    title: string;
    description: string;
    liveStatus: string;
    waitingStatus: string;
    noReportStatus: string;
  }
> = {
  zh: {
    title: "实时 RAG 遥测",
    description:
      "当前运行的证据遥测来自检索记录，这里不展示离线 benchmark 分数。",
    liveStatus: "实时运行数据",
    waitingStatus: "等待检索记录",
    noReportStatus: "暂无报告",
  },
  en: {
    title: "Live RAG Telemetry",
    description:
      "Current run evidence telemetry from retrieval records. No offline benchmark scores are shown here.",
    liveStatus: "Live run data",
    waitingStatus: "Waiting for retrieval records",
    noReportStatus: "Not reported",
  },
};

const METRIC_COPY: Record<RagEvalLocale, RagEvalMetricCopy[]> = {
  zh: [
    {
      key: "evidenceRetrieved",
      label: "已检索证据",
      detail: "检索返回的 SEC filing 证据块。",
      tone: "strong",
    },
    {
      key: "evidenceUsed",
      label: "已使用证据",
      detail: "保留在 evidence pack 中的 SEC filing 证据块。",
      tone: "stable",
    },
    {
      key: "metricFacts",
      label: "指标事实",
      detail: "Agent 可用的 SEC 或 market facts。",
      tone: "stable",
    },
    {
      key: "sectionsCovered",
      label: "覆盖章节",
      detail: "覆盖到的 filing sections 数量。",
      tone: "muted",
    },
    {
      key: "retrievalLatency",
      label: "检索延迟",
      detail: "retrieval 工具总耗时。",
      tone: "muted",
    },
    {
      key: "emptyRetrieval",
      label: "空检索",
      detail: "是否有任一步 retrieval 没有返回 evidence。",
      tone: "caution",
    },
    {
      key: "evidencePackSize",
      label: "证据包大小",
      detail: "序列化后的 evidence payload 大小。",
      tone: "muted",
    },
  ],
  en: [
    {
      key: "evidenceRetrieved",
      label: "Evidence Retrieved",
      detail: "Filing evidence chunks returned by retrieval.",
      tone: "strong",
    },
    {
      key: "evidenceUsed",
      label: "Evidence Used",
      detail: "Filing chunks kept in the evidence pack.",
      tone: "stable",
    },
    {
      key: "metricFacts",
      label: "Metric Facts",
      detail: "SEC or market facts available to the agent.",
      tone: "stable",
    },
    {
      key: "sectionsCovered",
      label: "Sections Covered",
      detail: "Distinct filing sections represented.",
      tone: "muted",
    },
    {
      key: "retrievalLatency",
      label: "Retrieval Latency",
      detail: "Total retrieval tool latency.",
      tone: "muted",
    },
    {
      key: "emptyRetrieval",
      label: "Empty Retrieval",
      detail: "Whether any retrieval step returned no evidence.",
      tone: "caution",
    },
    {
      key: "evidencePackSize",
      label: "Evidence Pack Size",
      detail: "Serialized evidence payload size.",
      tone: "muted",
    },
  ],
};

export function ragEvalDashboardTitle(locale: RagEvalLocale) {
  return DASHBOARD_COPY[locale].title;
}

export function ragEvalDashboardDescription(locale: RagEvalLocale) {
  return DASHBOARD_COPY[locale].description;
}

export function ragEvalDashboardStatusLabel(
  hasTelemetry: boolean,
  locale: RagEvalLocale,
) {
  if (!hasTelemetry) {
    return DASHBOARD_COPY[locale].waitingStatus;
  }
  return DASHBOARD_COPY[locale].liveStatus;
}

export function ragEvalDashboardReportCountLabel(
  reportCount: number | null,
  locale: RagEvalLocale,
) {
  if (reportCount === null) {
    return DASHBOARD_COPY[locale].noReportStatus;
  }
  return locale === "zh" ? `${reportCount} 份报告` : `${reportCount} reports`;
}

export function buildRagEvalMetricCopy(locale: RagEvalLocale) {
  return METRIC_COPY[locale];
}
