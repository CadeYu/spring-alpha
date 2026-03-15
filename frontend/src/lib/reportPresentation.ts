import type { SourceContext } from '@/types/AnalysisReport';

type SourceStatus = NonNullable<SourceContext['status']>;

const FISCAL_QUARTER_PATTERN = /^FY(\d{4})\s+Q([1-4])$/i;
const LEGACY_LIMITED_MESSAGE_PATTERN =
  /no high-confidence verbatim citations survived validation/i;
const SOURCE_STATUS_PRIORITY: Record<SourceStatus, number> = {
  UNAVAILABLE: 0,
  DEGRADED: 1,
  GROUNDED: 2,
  LIMITED: 3,
};

export function isQuarterlyPeriodLabel(period?: string | null): boolean {
  if (!period) {
    return false;
  }

  const normalized = period.trim().toUpperCase();
  return normalized.startsWith('Q') || FISCAL_QUARTER_PATTERN.test(normalized);
}

export function formatPeriodForDisplay(period?: string | null, lang: string = 'en'): string | undefined {
  if (!period) {
    return undefined;
  }

  const normalized = period.trim();
  const fiscalQuarterMatch = normalized.match(FISCAL_QUARTER_PATTERN);
  if (!fiscalQuarterMatch) {
    return normalized;
  }

  const [, year, quarter] = fiscalQuarterMatch;
  return lang === 'zh' ? `${year}财年Q${quarter}` : `FY${year} Q${quarter}`;
}

export function normalizeSourceStatus(sourceContext?: SourceContext | null): SourceStatus {
  if (sourceContext?.status === 'LIMITED') {
    return 'LIMITED';
  }

  if (
    sourceContext?.status === 'GROUNDED' &&
    LEGACY_LIMITED_MESSAGE_PATTERN.test(sourceContext.message || '')
  ) {
    return 'LIMITED';
  }

  return sourceContext?.status || 'UNAVAILABLE';
}

export function mergeSourceContexts(
  previous?: SourceContext | null,
  next?: SourceContext | null,
): SourceContext | undefined {
  if (!previous && !next) {
    return undefined;
  }
  if (!previous) {
    return next ? { ...next, status: normalizeSourceStatus(next) } : undefined;
  }
  if (!next) {
    return { ...previous, status: normalizeSourceStatus(previous) };
  }

  const previousStatus = normalizeSourceStatus(previous);
  const nextStatus = normalizeSourceStatus(next);

  if (SOURCE_STATUS_PRIORITY[nextStatus] > SOURCE_STATUS_PRIORITY[previousStatus]) {
    return {
      ...previous,
      ...next,
      status: nextStatus,
    };
  }

  if (SOURCE_STATUS_PRIORITY[nextStatus] < SOURCE_STATUS_PRIORITY[previousStatus]) {
    return {
      ...next,
      ...previous,
      status: previousStatus,
      message: previous.message?.trim() ? previous.message.trim() : next.message,
    };
  }

  return {
    ...previous,
    ...next,
    status: nextStatus,
    message: next.message?.trim() ? next.message.trim() : previous.message,
  };
}

export function getSourceStatusLabel(sourceContext: SourceContext | undefined, lang: string = 'en'): string {
  const status = normalizeSourceStatus(sourceContext);
  if (lang === 'zh') {
    switch (status) {
      case 'GROUNDED':
        return '来源已验证';
      case 'LIMITED':
        return '有来源依据，引用展示受限';
      case 'DEGRADED':
        return '降级模式';
      default:
        return '来源不可用';
    }
  }

  switch (status) {
    case 'GROUNDED':
      return 'grounded evidence verified';
    case 'LIMITED':
      return 'grounded evidence, citation display limited';
    case 'DEGRADED':
      return 'degraded mode';
    default:
      return 'source unavailable';
  }
}

export function getSourceMessage(sourceContext: SourceContext | undefined, lang: string = 'en'): string {
  const status = normalizeSourceStatus(sourceContext);

  if (status === 'LIMITED') {
    return lang === 'zh'
      ? '已检索到 SEC 原文证据，但本次没有筛出适合直接展示的高置信逐字引用；分析结论仍基于原始披露生成。'
      : 'SEC source evidence was retrieved, but this run did not retain a display-ready high-confidence verbatim quote. The analysis remains grounded in the filing.';
  }

  if (sourceContext?.message?.trim()) {
    const localizedKnownMessage = localizeKnownSourceMessage(sourceContext.message.trim(), status, lang);
    if (localizedKnownMessage) {
      return localizedKnownMessage;
    }
    return sourceContext.message.trim();
  }

  if (status === 'GROUNDED') {
    return lang === 'zh'
      ? '已检索到可验证的 SEC 原文证据。'
      : 'Grounded SEC evidence was retrieved for this run.';
  }

  if (status === 'DEGRADED') {
    return lang === 'zh'
      ? '本次分析采用降级模式运行，因此不展示可验证引用。'
      : 'This run operated in degraded mode, so verifiable citations are not shown.';
  }

  return lang === 'zh'
    ? '本次分析未能拿到可验证的 SEC 文本证据，因此不展示来源引用。'
    : 'This run could not obtain grounded SEC text evidence, so source citations are hidden.';
}

function localizeKnownSourceMessage(
  message: string,
  status: SourceStatus,
  lang: string,
): string | null {
  if (lang !== 'zh') {
    return null;
  }

  if (/semantic grounding was not ready yet/i.test(message)) {
    return 'SEC 文件已获取，但语义 grounding 尚未就绪。本次以降级模式运行，因此不展示可验证引用。';
  }

  if (/semantic sec retrieval failed/i.test(message)) {
    return '本次 SEC 语义检索失败，因此暂不展示可验证引用。';
  }

  if (/sec filing retrieval failed/i.test(message)) {
    return '本次未能获取 SEC 文件，因此报告仅基于财务数据生成，无法提供可验证引用。';
  }

  if (/cached sec vectors were rebuilt after an embedding dimension change/i.test(message)) {
    return '检测到 embedding 维度变化，SEC 向量缓存已重建。本次改用降级模式运行，暂不展示可验证引用。';
  }

  if (/analysis is preparing source evidence/i.test(message)) {
    return '分析正在准备来源证据。';
  }

  if (status === 'DEGRADED') {
    return '本次分析采用降级模式运行，因此不展示可验证引用。';
  }

  return null;
}
