const FISCAL_QUARTER_PATTERN = /^FY(\d{4})\s+Q([1-4])$/i;

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
