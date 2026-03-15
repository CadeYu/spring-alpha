'use client';

import { useCallback, useState } from 'react';
import { pdf } from '@react-pdf/renderer';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AnalysisReportPDF } from '@/components/pdf/AnalysisReportPDF';
import type { AnalysisReport } from '@/types/AnalysisReport';

interface PdfDownloadButtonProps {
  report: AnalysisReport;
  ticker: string;
  lang: string;
}

function buildFilename(ticker: string, lang: string): string {
  const today = new Date().toISOString().slice(0, 10);
  return lang === 'zh'
    ? `${ticker}_AI分析报告_${today}.pdf`
    : `${ticker}_AI_Analysis_Report_${today}.pdf`;
}

export function PdfDownloadButton({ report, ticker, lang }: PdfDownloadButtonProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const isZh = lang === 'zh';

  const handleDownload = useCallback(async () => {
    setIsGenerating(true);
    setErrorMessage(null);

    try {
      const blob = await pdf(
        <AnalysisReportPDF report={report} ticker={ticker} lang={lang} />
      ).toBlob();

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = buildFilename(ticker, lang);
      link.rel = 'noopener';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      console.error('PDF generation failed:', error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : (isZh ? 'PDF 导出失败，请稍后重试。' : 'PDF export failed. Please try again.')
      );
    } finally {
      setIsGenerating(false);
    }
  }, [isZh, lang, report, ticker]);

  return (
    <div className="flex flex-col items-end gap-2">
      <Button
        onClick={handleDownload}
        disabled={isGenerating}
        variant="ghost"
        className="bg-slate-800 border border-slate-700 text-emerald-400 hover:bg-slate-700 hover:text-emerald-300 hover:border-emerald-600/50 transition-all"
      >
        {isGenerating ? (
          <>
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            {isZh ? '正在生成 PDF...' : 'Generating PDF...'}
          </>
        ) : (
          <>📄 {isZh ? '下载 PDF 报告' : 'Download PDF'}</>
        )}
      </Button>
      {errorMessage ? (
        <p className="max-w-xs text-right text-xs text-red-400">
          {isZh ? `PDF 导出失败：${errorMessage}` : `PDF export failed: ${errorMessage}`}
        </p>
      ) : null}
    </div>
  );
}
