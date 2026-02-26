'use client';

import { useState, useCallback } from 'react';
import { pdf } from '@react-pdf/renderer';
import { AnalysisReportPDF } from '@/components/pdf/AnalysisReportPDF';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';
import type { AnalysisReport } from '@/types/AnalysisReport';

interface PdfDownloadButtonProps {
    report: AnalysisReport;
    ticker: string;
    lang: string;
}

export function PdfDownloadButton({ report, ticker, lang }: PdfDownloadButtonProps) {
    const [isGenerating, setIsGenerating] = useState(false);
    const isZh = lang === 'zh';

    const handleDownload = useCallback(async () => {
        setIsGenerating(true);
        try {
            const blob = await pdf(
                <AnalysisReportPDF report={report} ticker={ticker} lang={lang} />
            ).toBlob();

            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${ticker}_Analysis_Report_${new Date().toISOString().slice(0, 10)}.pdf`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (err) {
            console.error('PDF generation failed:', err);
        } finally {
            setIsGenerating(false);
        }
    }, [report, ticker, lang]);

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
                    {isZh ? '生成中...' : 'Generating...'}
                </>
            ) : (
                <>
                    📄 {isZh ? '下载 PDF 报告' : 'Download PDF'}
                </>
            )}
        </Button>
    );
}
