'use client';

import {
  Document,
  Font,
  Page,
  StyleSheet,
  Text,
  View,
} from '@react-pdf/renderer';
import type {
  AnalysisReport,
  BusinessSignalItem,
  BusinessSignals,
  Citation,
  CoreThesis,
  MetricInsight,
  SupportingEvidence,
} from '@/types/AnalysisReport';
import { formatPeriodForDisplay, getSourceMessage, getSourceStatusLabel } from '@/lib/reportPresentation';

function resolveArialUnicodeFontSrc(): string {
  if (typeof window === 'undefined' && typeof process !== 'undefined') {
    return `${process.cwd()}/public/fonts/ArialUnicode.ttf`;
  }
  return '/fonts/ArialUnicode.ttf';
}

Font.register({
  family: 'ArialUnicode',
  src: resolveArialUnicodeFontSrc(),
});

Font.registerHyphenationCallback?.((word) => [word]);

const POSTER_SIZE = { width: 1080, height: 1350 } as const;

const styles = StyleSheet.create({
  page: {
    position: 'relative',
    paddingTop: 34,
    paddingBottom: 28,
    paddingHorizontal: 34,
    backgroundColor: '#020617',
    color: '#e2e8f0',
    fontSize: 12,
    lineHeight: 1.45,
  },
  glowTop: {
    position: 'absolute',
    top: -120,
    right: -60,
    width: 420,
    height: 260,
    backgroundColor: '#0f766e',
    opacity: 0.1,
    borderRadius: 220,
  },
  glowBottom: {
    position: 'absolute',
    bottom: -120,
    left: -80,
    width: 360,
    height: 260,
    backgroundColor: '#1d4ed8',
    opacity: 0.08,
    borderRadius: 200,
  },
  tickerGhost: {
    position: 'absolute',
    top: 36,
    right: 34,
    fontSize: 126,
    fontWeight: 700,
    color: '#0d1a31',
    opacity: 0.44,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 18,
  },
  brandBlock: {
    width: '66%',
  },
  brandLabel: {
    fontSize: 11,
    color: '#2dd4bf',
    textTransform: 'uppercase',
    letterSpacing: 3,
    marginBottom: 8,
  },
  identity: {
    fontSize: 18,
    color: '#e2e8f0',
    marginBottom: 6,
  },
  generatedAt: {
    fontSize: 10.5,
    color: '#64748b',
  },
  chipStack: {
    alignItems: 'flex-end',
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    fontSize: 10,
    textTransform: 'uppercase',
    letterSpacing: 1.6,
    marginBottom: 8,
  },
  chipPositive: {
    backgroundColor: '#072f27',
    border: '1 solid #10b981',
    color: '#86efac',
  },
  chipMixed: {
    backgroundColor: '#33260f',
    border: '1 solid #f59e0b',
    color: '#fcd34d',
  },
  chipNegative: {
    backgroundColor: '#36111b',
    border: '1 solid #f43f5e',
    color: '#fda4af',
  },
  chipNeutral: {
    backgroundColor: '#0f172a',
    border: '1 solid #334155',
    color: '#cbd5e1',
  },
  heroCard: {
    borderRadius: 28,
    padding: 24,
    backgroundColor: '#061628',
    border: '1 solid #134e5e',
    marginBottom: 14,
  },
  heroGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'stretch',
  },
  heroGridZh: {
    flexDirection: 'column',
  },
  heroMain: {
    width: '68.5%',
    paddingRight: 16,
  },
  heroMainZh: {
    width: '100%',
    paddingRight: 0,
    marginBottom: 14,
  },
  heroAside: {
    width: '27.5%',
    borderRadius: 22,
    padding: 16,
    backgroundColor: '#04101d',
    border: '1 solid #18324a',
    justifyContent: 'space-between',
  },
  heroAsideZh: {
    width: '100%',
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: 'transparent',
    border: '0 solid transparent',
    padding: 0,
  },
  heroAsideCell: {
    width: '31.5%',
    borderRadius: 18,
    padding: 14,
    backgroundColor: '#04101d',
    border: '1 solid #18324a',
    minHeight: 108,
  },
  heroAsideBlock: {
    marginBottom: 14,
  },
  heroAsideLabel: {
    fontSize: 9.5,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 1.8,
    marginBottom: 8,
  },
  heroAsideValue: {
    fontSize: 30,
    lineHeight: 1.04,
    color: '#f8fafc',
    fontWeight: 700,
    marginBottom: 6,
  },
  heroAsideMeta: {
    fontSize: 11,
    lineHeight: 1.35,
    color: '#cbd5e1',
  },
  heroAsideSecondaryValue: {
    fontSize: 22,
    lineHeight: 1.08,
    color: '#f8fafc',
    fontWeight: 700,
    marginBottom: 6,
  },
  heroAsideDivider: {
    height: 1,
    backgroundColor: '#163047',
    marginVertical: 12,
  },
  heroKicker: {
    fontSize: 12,
    color: '#5eead4',
    textTransform: 'uppercase',
    letterSpacing: 2.4,
    marginBottom: 12,
  },
  companyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  tickerPill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    backgroundColor: '#0b2238',
    border: '1 solid #1e3a5f',
    marginRight: 10,
  },
  tickerPillText: {
    fontSize: 10,
    color: '#93c5fd',
    textTransform: 'uppercase',
    letterSpacing: 1.4,
  },
  heroCompany: {
    fontSize: 17,
    color: '#f8fafc',
    fontWeight: 700,
  },
  heroHeadline: {
    fontSize: 39,
    lineHeight: 1.07,
    color: '#f8fafc',
    fontWeight: 700,
    marginBottom: 12,
  },
  heroHeadlineZh: {
    fontSize: 29,
    lineHeight: 1.12,
    marginBottom: 12,
  },
  heroSummary: {
    fontSize: 12.5,
    lineHeight: 1.42,
    color: '#cbd5e1',
  },
  heroSummaryZh: {
    fontSize: 11,
    lineHeight: 1.48,
  },
  metricsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 14,
  },
  metricCard: {
    width: '23.6%',
    borderRadius: 22,
    paddingTop: 14,
    paddingRight: 14,
    paddingBottom: 16,
    paddingLeft: 14,
    backgroundColor: '#071121',
    border: '1 solid #17243a',
  },
  metricAccent: {
    width: 42,
    height: 4,
    borderRadius: 999,
    marginBottom: 12,
  },
  metricAccentRevenue: {
    backgroundColor: '#2dd4bf',
  },
  metricAccentMargin: {
    backgroundColor: '#38bdf8',
  },
  metricAccentIncome: {
    backgroundColor: '#a78bfa',
  },
  metricAccentGrowth: {
    backgroundColor: '#f59e0b',
  },
  metricLabel: {
    fontSize: 10,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 1.7,
    marginBottom: 10,
  },
  metricValue: {
    fontSize: 24,
    lineHeight: 1.05,
    color: '#f8fafc',
    fontWeight: 700,
    marginBottom: 6,
  },
  metricBody: {
    fontSize: 10.5,
    lineHeight: 1.32,
    color: '#cbd5e1',
  },
  sectionCard: {
    borderRadius: 24,
    padding: 14,
    backgroundColor: '#071121',
    border: '1 solid #17243a',
    marginBottom: 14,
  },
  sectionLabel: {
    fontSize: 11.5,
    color: '#2dd4bf',
    textTransform: 'uppercase',
    letterSpacing: 2.1,
    marginBottom: 10,
  },
  questionGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
  },
  questionCard: {
    width: '48.7%',
    borderRadius: 18,
    padding: 12,
    backgroundColor: '#03101e',
    border: '1 solid #17243a',
    minHeight: 134,
    marginBottom: 10,
  },
  questionCardZh: {
    minHeight: 156,
  },
  questionAccent: {
    width: 28,
    height: 3,
    borderRadius: 999,
    marginBottom: 8,
  },
  questionAccentWhatChanged: {
    backgroundColor: '#2dd4bf',
  },
  questionAccentDrivers: {
    backgroundColor: '#38bdf8',
  },
  questionAccentStrategicBets: {
    backgroundColor: '#e879f9',
  },
  questionAccentWatchItems: {
    backgroundColor: '#f59e0b',
  },
  questionLabel: {
    fontSize: 9.7,
    color: '#e2e8f0',
    textTransform: 'uppercase',
    letterSpacing: 1.8,
    marginBottom: 8,
  },
  questionLabelZh: {
    letterSpacing: 1,
  },
  questionItem: {
    borderRadius: 14,
    padding: 8,
    backgroundColor: '#071121',
    border: '1 solid #17243a',
    marginBottom: 6,
  },
  questionItemLabel: {
    fontSize: 9,
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 1.3,
    marginBottom: 4,
  },
  questionItemLabelZh: {
    letterSpacing: 0.8,
  },
  questionItemText: {
    fontSize: 10.1,
    lineHeight: 1.31,
    color: '#e2e8f0',
  },
  questionItemTextZh: {
    fontSize: 9.3,
    lineHeight: 1.34,
  },
  debateRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  debateCard: {
    width: '48.7%',
    borderRadius: 22,
    padding: 14,
    minHeight: 84,
  },
  debateCardZh: {
    minHeight: 94,
  },
  debateBull: {
    backgroundColor: '#08281e',
    border: '1 solid #22c55e',
  },
  debateBear: {
    backgroundColor: '#2b0f1a',
    border: '1 solid #f43f5e',
  },
  debateLabel: {
    fontSize: 11,
    color: '#f8fafc',
    textTransform: 'uppercase',
    letterSpacing: 1.8,
    marginBottom: 10,
  },
  debateBody: {
    fontSize: 11.2,
    lineHeight: 1.34,
    color: '#e2e8f0',
  },
  debateBodyZh: {
    fontSize: 10.1,
    lineHeight: 1.32,
  },
  footerStrip: {
    width: '100%',
  },
  footerCard: {
    borderRadius: 22,
    padding: 12,
    backgroundColor: '#071121',
    border: '1 solid #12384b',
  },
  footerTitle: {
    fontSize: 11,
    color: '#2dd4bf',
    textTransform: 'uppercase',
    letterSpacing: 1.9,
    marginBottom: 8,
  },
  watchPill: {
    borderRadius: 16,
    padding: 12,
    backgroundColor: '#020b1c',
    border: '1 solid #17243a',
  },
  watchText: {
    fontSize: 11.5,
    lineHeight: 1.42,
    color: '#dbeafe',
  },
  sourceTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  sourceStatus: {
    fontSize: 10,
    color: '#5eead4',
    textTransform: 'uppercase',
    letterSpacing: 1.6,
  },
  sourceText: {
    fontSize: 10.8,
    lineHeight: 1.32,
    color: '#e2e8f0',
    marginBottom: 5,
  },
  sourceTextZh: {
    fontSize: 10.1,
    lineHeight: 1.34,
  },
  sourceHint: {
    fontSize: 9.2,
    lineHeight: 1.24,
    color: '#64748b',
  },
});

interface AnalysisReportPDFProps {
  report: AnalysisReport;
  ticker: string;
  lang: string;
}

type SignalGroupKey =
  | 'segmentPerformance'
  | 'productServiceUpdates'
  | 'managementFocus'
  | 'strategicMoves'
  | 'capexSignals'
  | 'riskSignals';

type QuestionKey = 'whatChanged' | 'drivers' | 'strategicBets' | 'watchItems';

interface PosterQuestionItem {
  label?: string;
  body: string;
}

interface PosterQuestionSection {
  key: QuestionKey;
  title: string;
  items: PosterQuestionItem[];
}

type PosterDensity = 'default' | 'tight';

function getFontFamily(lang: string): string {
  return lang === 'zh' ? 'ArialUnicode' : 'Helvetica';
}

function t(lang: string, en: string, zh: string): string {
  return lang === 'zh' ? zh : en;
}

function verdictLabel(thesis: CoreThesis | undefined, lang: string): string {
  switch (thesis?.verdict) {
    case 'positive':
      return t(lang, 'Positive setup', '偏多判断');
    case 'negative':
      return t(lang, 'Pressure zone', '承压判断');
    default:
      return t(lang, 'Mixed setup', '中性偏谨慎');
  }
}

function verdictStyle(thesis: CoreThesis | undefined) {
  switch (thesis?.verdict) {
    case 'positive':
      return styles.chipPositive;
    case 'negative':
      return styles.chipNegative;
    default:
      return styles.chipMixed;
  }
}

function shortenText(value: string | undefined, maxLength: number): string {
  if (!value) return '';
  const trimmed = value.replace(/\s+/g, ' ').trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, maxLength - 1).trimEnd()}...`;
}

function splitSentences(summary?: string): string[] {
  if (!summary) return [];
  return summary
    .split(/(?<=[。！？.!?])\s*/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function formatGeneratedAt(value?: string, lang = 'en'): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return lang === 'zh'
    ? date.toLocaleString('zh-CN')
    : date.toLocaleString('en-US');
}

function formatSignalText(item?: BusinessSignalItem, lang = 'en', withTitle = true): string | null {
  if (!item) return null;

  const title = item.title?.trim();
  const detail = item.summary?.trim() || item.evidenceSnippet?.trim();

  if (title && detail) {
    if (!withTitle || detail.toLowerCase().startsWith(title.toLowerCase())) {
      return detail;
    }
    return `${title}${lang === 'zh' ? '：' : ': '}${detail}`;
  }

  return title || detail || null;
}

function extractSignalBullets(
  businessSignals: BusinessSignals | undefined,
  groups: SignalGroupKey[],
  limit: number,
  lang: string
): string[] {
  if (!businessSignals) return [];

  const seen = new Set<string>();
  const bullets: string[] = [];

  for (const groupName of groups) {
    const group = businessSignals[groupName] ?? [];
    for (const item of group) {
      const text = formatSignalText(item, lang);
      if (!text || seen.has(text)) {
        continue;
      }
      seen.add(text);
      bullets.push(text);
      if (bullets.length >= limit) {
        return bullets;
      }
    }
  }

  return bullets;
}

function extractSignalEvidence(
  businessSignals: BusinessSignals | undefined,
  groups: SignalGroupKey[],
  limit: number,
  lang: string,
  fallbackLabel: string
): SupportingEvidence[] {
  if (!businessSignals) return [];

  const seen = new Set<string>();
  const evidence: SupportingEvidence[] = [];

  for (const groupName of groups) {
    const group = businessSignals[groupName] ?? [];
    for (const item of group) {
      const label = item.title?.trim() || fallbackLabel;
      const detail = item.summary?.trim() || item.evidenceSnippet?.trim();
      const key = `${label}::${detail}`;
      if (!detail || seen.has(key)) {
        continue;
      }
      seen.add(key);
      evidence.push({ label, detail });
      if (evidence.length >= limit) {
        return evidence;
      }
    }
  }

  return evidence;
}

function cleanEvidence(items?: SupportingEvidence[]): SupportingEvidence[] {
  return items?.filter((item) => item?.detail?.trim()) ?? [];
}

function normalizeBulletKey(value?: string): string | null {
  if (!value) return null;
  const normalized = value
    .trim()
    .replace(/[“”‘’]/g, '"')
    .replace(/"[^"]+"/g, '"quoted"')
    .replace(/\s+/g, ' ')
    .replace(/[，,。.!?；;：:]/g, '')
    .toLowerCase();
  return normalized || null;
}

function dedupeBullets(values: string[]): string[] {
  const seen = new Set<string>();
  const deduped: string[] = [];
  for (const value of values) {
    const trimmed = value?.trim();
    const key = normalizeBulletKey(trimmed);
    if (!trimmed || !key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(trimmed);
  }
  return deduped;
}

function estimatePosterWeight(report: AnalysisReport): number {
  const thesis = report.coreThesis;
  const textBits = [
    thesis?.headline,
    thesis?.summary,
    report.executiveSummary,
    report.bullCase,
    report.bearCase,
    ...(thesis?.whatChanged ?? []),
    ...(thesis?.keyPoints ?? []),
    ...(thesis?.watchItems ?? []),
    ...(thesis?.drivers?.map((item) => item.detail) ?? []),
    ...(thesis?.strategicBets?.map((item) => item.detail) ?? []),
    ...(thesis?.supportingEvidence?.map((item) => item.detail) ?? []),
    ...(report.citations ?? []).flatMap((citation) => [citation.excerpt, citation.excerptZh]),
  ];

  const totalChars = textBits
    .filter(Boolean)
    .reduce((sum, value) => sum + (value?.trim().length ?? 0), 0);

  const itemCount =
    (thesis?.whatChanged?.length ?? 0) +
    (thesis?.drivers?.length ?? 0) +
    (thesis?.strategicBets?.length ?? 0) +
    (thesis?.watchItems?.length ?? 0);

  return totalChars + itemCount * 24;
}

function pickPosterDensity(report: AnalysisReport, lang: string): PosterDensity {
  const weight = estimatePosterWeight(report);
  const threshold = lang === 'zh' ? 360 : 440;
  return weight > threshold ? 'tight' : 'default';
}

function compactQuestionBullets(
  items: string[],
  lang: string,
  density: PosterDensity,
  limit = density === 'tight' ? 1 : 2
): PosterQuestionItem[] {
  const bodyLimit = density === 'tight'
    ? (lang === 'zh' ? 38 : 56)
    : (lang === 'zh' ? 56 : 78);

  return items
    .filter(Boolean)
    .slice(0, limit)
    .map((body) => ({
      body: shortenText(body, bodyLimit),
    }));
}

function compactQuestionEvidence(
  items: SupportingEvidence[],
  lang: string,
  density: PosterDensity,
  limit = density === 'tight' ? 1 : 2
): PosterQuestionItem[] {
  const bodyLimit = density === 'tight'
    ? (lang === 'zh' ? 34 : 50)
    : (lang === 'zh' ? 52 : 72);

  return items
    .filter((item) => item?.detail?.trim())
    .slice(0, limit)
    .map((item) => ({
      label: item.label?.trim(),
      body: shortenText(item.detail, bodyLimit),
    }));
}

function buildQuestionSections(report: AnalysisReport, lang: string, density: PosterDensity): PosterQuestionSection[] {
  const isZh = lang === 'zh';
  const whatChanged = dedupeBullets(report.coreThesis?.whatChanged?.filter(Boolean) ?? []);
  const legacyKeyPoints = dedupeBullets(report.coreThesis?.keyPoints?.filter(Boolean) ?? []);
  const watchItems = dedupeBullets(report.coreThesis?.watchItems?.filter(Boolean) ?? []);
  const drivers = cleanEvidence(report.coreThesis?.drivers);
  const strategicBets = cleanEvidence(report.coreThesis?.strategicBets);
  const legacyEvidence = cleanEvidence(report.coreThesis?.supportingEvidence);
  const businessSignals = report.businessSignals;

  const displayedWhatChanged =
    whatChanged.length > 0
      ? compactQuestionBullets(whatChanged, lang, density)
      : legacyKeyPoints.length > 0
        ? compactQuestionBullets(legacyKeyPoints, lang, density)
        : (() => {
            const signalFallback = extractSignalBullets(
              businessSignals,
              ['segmentPerformance', 'productServiceUpdates'],
              density === 'tight' ? 1 : 2,
              lang
            );
            if (signalFallback.length > 0) {
              return compactQuestionBullets(signalFallback, lang, density);
            }

            const summaryFallback = splitSentences(report.coreThesis?.summary || report.executiveSummary);
            if (summaryFallback.length > 0) {
              return compactQuestionBullets(summaryFallback, lang, density);
            }

            return [
              {
                body: t(
                  lang,
                  'The quarter did not produce a clean business summary.',
                  '本季还没有沉淀出足够清晰的业务主线。'
                ),
              },
            ];
          })();

  const displayedDrivers =
    drivers.length > 0
      ? compactQuestionEvidence(drivers, lang, density)
      : legacyEvidence.length > 0
        ? compactQuestionEvidence(legacyEvidence, lang, density)
        : (() => {
            const signalFallback = extractSignalEvidence(
              businessSignals,
              ['managementFocus', 'segmentPerformance', 'productServiceUpdates'],
              density === 'tight' ? 1 : 2,
              lang,
              isZh ? '核心驱动' : 'Core Driver'
            );
            if (signalFallback.length > 0) {
              return compactQuestionEvidence(signalFallback, lang, density);
            }

            return [
              {
                label: t(lang, 'Driver', '驱动因素'),
                body: t(
                  lang,
                  'Demand, pricing, and expense mix remain the main variables behind the print.',
                  '需求、定价和费用结构仍是解释本季表现的核心变量。'
                ),
              },
            ];
          })();

  const displayedStrategicBets =
    strategicBets.length > 0
      ? compactQuestionEvidence(strategicBets, lang, density)
      : (() => {
          const signalFallback = extractSignalEvidence(
            businessSignals,
            ['strategicMoves', 'capexSignals', 'productServiceUpdates'],
            density === 'tight' ? 1 : 2,
            lang,
            isZh ? '战略押注' : 'Strategic Bet'
          );
          if (signalFallback.length > 0) {
            return compactQuestionEvidence(signalFallback, lang, density);
          }
          if (legacyEvidence.length > displayedDrivers.length) {
            return compactQuestionEvidence(legacyEvidence.slice(displayedDrivers.length), lang, density);
          }

          return [
            {
              label: t(lang, 'Management focus', '管理层方向'),
              body: t(
                lang,
                'Management is still deploying capital toward product, infrastructure, or go-to-market bets that shape the next leg of growth.',
                '管理层仍在把资源投向产品、基础设施或商业化能力，这会决定下一阶段增长质量。'
              ),
            },
          ];
        })();

  const displayedWatchItems =
    watchItems.length > 0
      ? compactQuestionBullets(watchItems, lang, density)
      : (() => {
          const signalFallback = extractSignalBullets(
            businessSignals,
            ['riskSignals', 'capexSignals', 'strategicMoves'],
            density === 'tight' ? 1 : 2,
            lang
          );
          if (signalFallback.length > 0) {
            return compactQuestionBullets(signalFallback, lang, density);
          }
          return [
            {
              body: t(
                lang,
                'Watch whether the current revenue, margin, and investment setup can hold into the next print.',
                '关注下一季营收、利润率和投入节奏能否继续同时成立。'
              ),
            },
          ];
        })();

  return [
    {
      key: 'whatChanged',
      title: t(lang, 'What Changed', '本季发生了什么'),
      items: displayedWhatChanged,
    },
    {
      key: 'drivers',
      title: t(lang, 'What Drove It', '核心驱动因素'),
      items: displayedDrivers,
    },
    {
      key: 'strategicBets',
      title: t(lang, 'What Is The Bet', '公司在押注什么'),
      items: displayedStrategicBets,
    },
    {
      key: 'watchItems',
      title: t(lang, 'What To Watch', '后续跟踪什么'),
      items: displayedWatchItems,
    },
  ];
}

function compactCitation(citations: Citation[], lang: string, density: PosterDensity): string | null {
  const candidate =
    lang === 'zh'
      ? citations.find((citation) => citation.excerptZh)
      : citations.find((citation) => citation.excerptZh || citation.excerpt);
  if (!candidate) return null;

  const body = lang === 'zh' && candidate.excerptZh ? candidate.excerptZh : candidate.excerpt;
  return shortenText(
    body,
    density === 'tight'
      ? (lang === 'zh' ? 52 : 88)
      : (lang === 'zh' ? 74 : 112)
  );
}

function compactMetric(metric: MetricInsight, lang: string): MetricInsight {
  return {
    ...metric,
    interpretation: shortenText(metric.interpretation, lang === 'zh' ? 20 : 22),
  };
}

function normalizeMetricName(metricName: string): string {
  const lower = metricName.toLowerCase().replace(/\s+/g, ' ').trim();

  if (
    lower.includes('营收同比') ||
    lower.includes('收入同比') ||
    lower.includes('同比增长') ||
    lower.includes('revenue yoy') ||
    lower.includes('revenue growth') ||
    (lower.includes('revenue') && lower.includes('yoy'))
  ) {
    return 'revenue_yoy';
  }

  if (lower.includes('营收') || lower.includes('收入') || lower === 'revenue' || lower.includes('total revenue')) {
    return 'revenue';
  }

  if (lower.includes('毛利率') || lower.includes('gross margin')) {
    return 'gross_margin';
  }

  if (
    lower.includes('净利润') ||
    lower.includes('净收入') ||
    lower.includes('net income') ||
    lower.includes('net profit')
  ) {
    return 'net_income';
  }

  if (lower.includes('现金流') || lower.includes('cash flow')) {
    return 'cash_flow';
  }

  return lower;
}

function metricCaption(metricName: string, lang: string): string {
  const normalized = normalizeMetricName(metricName);
  if (normalized === 'revenue_yoy') {
    return t(lang, 'Growth momentum', '增长动能');
  }
  if (normalized === 'revenue') {
    return t(lang, 'Demand pulse', '需求强度');
  }
  if (normalized === 'gross_margin') {
    return t(lang, 'Pricing power', '定价能力');
  }
  if (normalized === 'net_income') {
    return t(lang, 'Profit engine', '利润引擎');
  }
  return t(lang, 'Core metric', '核心指标');
}

function metricAccentStyle(metricName: string) {
  const normalized = normalizeMetricName(metricName);
  if (normalized === 'revenue_yoy') return styles.metricAccentGrowth;
  if (normalized === 'revenue') return styles.metricAccentRevenue;
  if (normalized === 'gross_margin') return styles.metricAccentMargin;
  if (normalized === 'net_income') return styles.metricAccentIncome;
  return styles.metricAccentRevenue;
}

function buildFallbackMetrics(lang: string): MetricInsight[] {
  return [
    {
      metricName: t(lang, 'Revenue', '营收'),
      value: '--',
      interpretation: t(lang, 'Revenue remains the anchor metric in this print.', '营收仍是本期最核心的锚点指标。'),
      sentiment: 'neutral',
    },
    {
      metricName: t(lang, 'Gross Margin', '毛利率'),
      value: '--',
      interpretation: t(lang, 'Margin quality still frames the debate.', '利润率质量仍决定市场叙事。'),
      sentiment: 'neutral',
    },
    {
      metricName: t(lang, 'Net Income', '净利润'),
      value: '--',
      interpretation: t(lang, 'Bottom-line resilience remains central.', '净利润韧性仍是关键观察点。'),
      sentiment: 'neutral',
    },
    {
      metricName: t(lang, 'Revenue YoY', '营收同比'),
      value: '--',
      interpretation: t(lang, 'Growth direction sets the tone.', '增长方向决定本季主基调。'),
      sentiment: 'neutral',
    },
  ];
}

function buildPosterMetrics(report: AnalysisReport, lang: string): MetricInsight[] {
  const fallback = buildFallbackMetrics(lang);
  const metrics = report.keyMetrics.map((metric) => compactMetric(metric, lang));
  if (metrics.length >= 4) return metrics.slice(0, 4);

  return [...metrics, ...fallback.slice(metrics.length, 4)];
}

function pickMetric(metrics: MetricInsight[], matcher: (name: string) => boolean): MetricInsight | undefined {
  return metrics.find((metric) => matcher(normalizeMetricName(metric.metricName)));
}

export function AnalysisReportPDF({ report, ticker, lang }: AnalysisReportPDFProps) {
  const isZh = lang === 'zh';
  const fontFamily = getFontFamily(lang);
  const density = pickPosterDensity(report, lang);
  const identity = [report.companyName || ticker, formatPeriodForDisplay(report.period, lang), report.filingDate]
    .filter(Boolean)
    .join(' · ');
  const generatedAt = formatGeneratedAt(report.metadata?.generatedAt, lang);
  const metrics = buildPosterMetrics(report, lang);
  const revenueMetric = pickMetric(metrics, (name) => name === 'revenue');
  const growthMetric = pickMetric(metrics, (name) => name === 'revenue_yoy');
  const profitMetric = pickMetric(metrics, (name) => name === 'net_income');
  const questionSections = buildQuestionSections(report, lang, density);
  const citation = compactCitation(report.citations || [], lang, density);
  const fallbackSourceContext = report.sourceContext || { status: citation ? 'GROUNDED' : 'UNAVAILABLE' as const };
  const sourceStatus = getSourceStatusLabel(fallbackSourceContext, lang);
  const sourceMessage = getSourceMessage(fallbackSourceContext, lang);
  const heroGridStyle = isZh ? [styles.heroGrid, styles.heroGridZh] : [styles.heroGrid];
  const heroMainStyle = isZh ? [styles.heroMain, styles.heroMainZh] : [styles.heroMain];
  const heroAsideStyle = isZh ? [styles.heroAside, styles.heroAsideZh] : [styles.heroAside];
  const heroHeadlineStyle = isZh ? [styles.heroHeadline, styles.heroHeadlineZh] : [styles.heroHeadline];
  const heroSummaryStyle = isZh ? [styles.heroSummary, styles.heroSummaryZh] : [styles.heroSummary];
  const questionCardStyle = isZh ? [styles.questionCard, styles.questionCardZh] : [styles.questionCard];
  const questionLabelStyle = isZh ? [styles.questionLabel, styles.questionLabelZh] : [styles.questionLabel];
  const questionItemLabelStyle = isZh
    ? [styles.questionItemLabel, styles.questionItemLabelZh]
    : [styles.questionItemLabel];
  const questionItemTextStyle = isZh
    ? [styles.questionItemText, styles.questionItemTextZh]
    : [styles.questionItemText];
  const bullCardStyle = isZh
    ? [styles.debateCard, styles.debateBull, styles.debateCardZh]
    : [styles.debateCard, styles.debateBull];
  const bearCardStyle = isZh
    ? [styles.debateCard, styles.debateBear, styles.debateCardZh]
    : [styles.debateCard, styles.debateBear];
  const debateBodyStyle = isZh ? [styles.debateBody, styles.debateBodyZh] : [styles.debateBody];
  const sourceTextStyle = isZh ? [styles.sourceText, styles.sourceTextZh] : [styles.sourceText];

  const heroSummary = shortenText(
    report.coreThesis?.summary ||
      report.executiveSummary ||
      t(lang, 'No concise thesis was generated for this run.', '本次运行未生成清晰结论。'),
    density === 'tight'
      ? (lang === 'zh' ? 68 : 84)
      : (lang === 'zh' ? 90 : 112)
  );
  const heroHeadline = shortenText(
    report.coreThesis?.headline || report.executiveSummary || ticker,
    density === 'tight'
      ? (lang === 'zh' ? 34 : 58)
      : (lang === 'zh' ? 44 : 72)
  );
  const bullCase = shortenText(
    report.bullCase,
    density === 'tight'
      ? (lang === 'zh' ? 28 : 44)
      : (lang === 'zh' ? 44 : 64)
  );
  const bearCase = shortenText(
    report.bearCase,
    density === 'tight'
      ? (lang === 'zh' ? 28 : 44)
      : (lang === 'zh' ? 44 : 64)
  );

  return (
    <Document
      title={`${ticker} ${t(lang, 'AI Poster', 'AI 海报简报')}`}
      author="Spring Alpha"
      subject={t(lang, `${ticker} social poster`, `${ticker} 社交传播海报`)}
    >
      <Page size={POSTER_SIZE} style={[styles.page, { fontFamily }]} wrap={false}>
        <View style={styles.glowTop} />
        <View style={styles.glowBottom} />
        <Text style={styles.tickerGhost}>{ticker}</Text>

        <View style={styles.headerRow}>
          <View style={styles.brandBlock}>
            <Text style={styles.brandLabel}>{t(lang, 'AI Earnings Poster', 'AI 财报海报')}</Text>
            <Text style={styles.identity}>{identity}</Text>
            <Text style={styles.generatedAt}>
              {t(lang, 'Generated', '生成于')} {generatedAt}
            </Text>
          </View>

          <View style={styles.chipStack}>
            <Text style={[styles.chip, verdictStyle(report.coreThesis)]}>
              {verdictLabel(report.coreThesis, lang)}
            </Text>
            <Text style={[styles.chip, styles.chipNeutral]}>
              {t(lang, 'Latest quarter', '最新季报')}
            </Text>
          </View>
        </View>

        <View style={styles.heroCard}>
          <Text style={styles.heroKicker}>{t(lang, 'The business in one read', '这一季的业务主线')}</Text>
          <View style={heroGridStyle}>
            <View style={heroMainStyle}>
              <View style={styles.companyRow}>
                <View style={styles.tickerPill}>
                  <Text style={styles.tickerPillText}>{ticker}</Text>
                </View>
                <Text style={styles.heroCompany}>{report.companyName || ticker}</Text>
              </View>
              <Text style={heroHeadlineStyle}>{heroHeadline}</Text>
              <Text style={heroSummaryStyle}>{heroSummary}</Text>
            </View>

            <View style={heroAsideStyle}>
              <View style={isZh ? styles.heroAsideCell : undefined}>
                <View style={styles.heroAsideBlock}>
                  <Text style={styles.heroAsideLabel}>{t(lang, 'Growth print', '主增长数字')}</Text>
                  <Text style={styles.heroAsideValue}>{growthMetric?.value || '--'}</Text>
                  <Text style={styles.heroAsideMeta}>{t(lang, 'Revenue YoY growth', '营收同比增长')}</Text>
                </View>
              </View>

              {!isZh ? <View style={styles.heroAsideDivider} /> : null}

              <View style={isZh ? styles.heroAsideCell : undefined}>
                <View style={styles.heroAsideBlock}>
                  <Text style={styles.heroAsideLabel}>{t(lang, 'Scale this quarter', '本季规模')}</Text>
                  <Text style={styles.heroAsideSecondaryValue}>{revenueMetric?.value || '--'}</Text>
                  <Text style={styles.heroAsideMeta}>{t(lang, 'Quarterly revenue', '季度营收规模')}</Text>
                </View>
              </View>

              <View style={isZh ? styles.heroAsideCell : undefined}>
                <View>
                  <Text style={styles.heroAsideLabel}>{t(lang, 'Profit this quarter', '本季盈利')}</Text>
                  <Text style={styles.heroAsideSecondaryValue}>{profitMetric?.value || '--'}</Text>
                  <Text style={styles.heroAsideMeta}>
                    {profitMetric
                      ? t(lang, 'Net income', '净利润')
                      : verdictLabel(report.coreThesis, lang)}
                  </Text>
                </View>
              </View>
            </View>
          </View>
        </View>

          <View style={styles.metricsRow}>
          {metrics.map((metric) => (
            <View key={metric.metricName} style={styles.metricCard}>
              <View style={[styles.metricAccent, metricAccentStyle(metric.metricName)]} />
              <Text style={styles.metricLabel}>{metric.metricName}</Text>
              <Text style={styles.metricValue}>{metric.value}</Text>
              <Text style={styles.metricBody}>{metricCaption(metric.metricName, lang)}</Text>
            </View>
          ))}
        </View>

        <View style={styles.sectionCard}>
          <Text style={styles.sectionLabel}>{t(lang, 'Four questions that frame the quarter', '四个最值得先看的问题')}</Text>
          <View style={styles.questionGrid}>
            {questionSections.map((section) => (
              <View key={section.key} style={questionCardStyle}>
                <View
                  style={[
                    styles.questionAccent,
                    section.key === 'whatChanged'
                      ? styles.questionAccentWhatChanged
                      : section.key === 'drivers'
                        ? styles.questionAccentDrivers
                        : section.key === 'strategicBets'
                          ? styles.questionAccentStrategicBets
                          : styles.questionAccentWatchItems,
                  ]}
                />
                <Text style={questionLabelStyle}>{section.title}</Text>
                {section.items.map((item, index) => (
                  <View key={`${section.key}-${index}`} style={styles.questionItem}>
                    {item.label ? <Text style={questionItemLabelStyle}>{item.label}</Text> : null}
                    <Text style={questionItemTextStyle}>{item.body}</Text>
                  </View>
                ))}
              </View>
            ))}
          </View>
        </View>

        <View style={styles.debateRow}>
          <View style={bullCardStyle}>
            <Text style={styles.debateLabel}>{t(lang, 'Bull case', '看多逻辑')}</Text>
            <Text style={debateBodyStyle}>{bullCase}</Text>
          </View>

          <View style={bearCardStyle}>
            <Text style={styles.debateLabel}>{t(lang, 'Bear case', '看空逻辑')}</Text>
            <Text style={debateBodyStyle}>{bearCase}</Text>
          </View>
        </View>

        <View style={styles.footerStrip}>
          <View style={styles.footerCard}>
            <View style={styles.sourceTop}>
              <Text style={styles.footerTitle}>{t(lang, 'Source check', '来源校验')}</Text>
              <Text style={styles.sourceStatus}>{sourceStatus}</Text>
            </View>
            <Text style={sourceTextStyle}>{citation || sourceMessage}</Text>
          </View>
        </View>
      </Page>
    </Document>
  );
}
