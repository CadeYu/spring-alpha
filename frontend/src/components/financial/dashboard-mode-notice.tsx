'use client';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import type { DashboardMode } from '@/types/FinancialFacts';
import { Ban, Landmark } from 'lucide-react';

interface DashboardModeNoticeProps {
  mode: Exclude<DashboardMode, 'standard'>;
  lang?: string;
  message?: string | null;
}

export function DashboardModeNotice({
  mode,
  lang = 'en',
  message,
}: DashboardModeNoticeProps) {
  const isZh = lang === 'zh';
  const isUnsupportedReit = mode === 'unsupported_reit';
  const Icon = isUnsupportedReit ? Ban : Landmark;
  const fallbackDescription = isUnsupportedReit
    ? (isZh
      ? '该 ticker 被识别为 REIT / Trust 类型，当前普通经营性公司仪表盘已禁用。'
      : 'This ticker was identified as a REIT / trust-like issuer, so the generic operating-company dashboard is disabled.')
    : (isZh
      ? '该 ticker 属于金融行业，通用毛利率、现金转化和雷达评分已隐藏，以避免误导性展示。'
      : 'This ticker is running in financial sector mode, so generic margin, cash-conversion, and radar views are hidden to avoid misleading output.');

  const title = isUnsupportedReit
    ? (isZh ? '当前不支持的证券类型' : 'Unsupported Security Type')
    : (isZh ? '金融行业模式' : 'Financial Sector Mode');

  const hasChineseMessage = Boolean(message && /[\u3400-\u9FFF]/.test(message));
  const description = isZh
    ? (hasChineseMessage ? message : fallbackDescription)
    : (message || fallbackDescription);

  return (
    <Alert className="border-amber-500/30 bg-amber-950/20 text-amber-100">
      <Icon className="h-4 w-4 text-amber-300" />
      <AlertTitle className="text-amber-200">{title}</AlertTitle>
      <AlertDescription className="text-amber-100/80">
        <p>{description}</p>
      </AlertDescription>
    </Alert>
  );
}
