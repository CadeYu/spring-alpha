'use client';

import { useState, useCallback } from 'react';
import { pdf } from '@react-pdf/renderer';
import { AnalysisReportPDF } from '@/components/pdf/AnalysisReportPDF';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import type { AnalysisReport } from '@/types/AnalysisReport';
import html2canvas from 'html2canvas';

interface PdfDownloadButtonProps {
    report: AnalysisReport;
    ticker: string;
    lang: string;
}

/** Chart element IDs to capture */
const CHART_IDS = ['chart-dupont', 'chart-radar'] as const;

/** Capture a DOM element as a base64 PNG data URL */
async function captureChart(elementId: string): Promise<string | null> {
    const el = document.getElementById(elementId);
    if (!el) return null;
    try {
        const canvas = await html2canvas(el, {
            backgroundColor: '#0f172a',  // match dark bg (slate-900)
            scale: 2,                     // 2x for clarity
            useCORS: true,
            logging: false,
        });
        return canvas.toDataURL('image/png');
    } catch (e) {
        console.warn(`Failed to capture ${elementId}:`, e);
        return null;
    }
}

export function PdfDownloadButton({ report, ticker, lang }: PdfDownloadButtonProps) {
    const [isGenerating, setIsGenerating] = useState(false);
    const isZh = lang === 'zh';

    const handleDownload = useCallback(async () => {
        setIsGenerating(true);
        try {
            // Step 1: Capture chart screenshots from the DOM
            const chartImages: Record<string, string> = {};
            for (const id of CHART_IDS) {
                const dataUrl = await captureChart(id);
                if (dataUrl) chartImages[id] = dataUrl;
            }

            // Step 2: Generate PDF with captured chart images
            const blob = await pdf(
                <AnalysisReportPDF
                    report={report}
                    ticker={ticker}
                    lang={lang}
                    chartImages={chartImages}
                />
            ).toBlob();

            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = isZh
                ? `${ticker}_AI分析报告_${new Date().toISOString().slice(0, 10)}.pdf`
                : `${ticker}_Analysis_Report_${new Date().toISOString().slice(0, 10)}.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('PDF generation failed:', err);
        } finally {
            setIsGenerating(false);
        }
    }, [report, ticker, lang, isZh]);

    return (
        <Button
            onClick={handleDownload}
            disabled={isGenerating}
            variant="ghost"
            className="bg-slate-800 border border-slate-700 text-emerald-400 hover:bg-slate-700 hover:text-emerald-300 hover:border-emerald-600/50 transition-all"
        >
            {isGenerating ? (
                <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    {isZh ? '截图并生成PDF中...' : 'Capturing & Generating...'}
                </>
            ) : (
                <>
                    📄 {isZh ? '下载 PDF 报告' : 'Download PDF'}
                </>
            )}
        </Button>
    );
}
