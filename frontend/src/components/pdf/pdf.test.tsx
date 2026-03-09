import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AnalysisReportPDF } from '@/components/pdf/AnalysisReportPDF';
import { PdfDownloadButton } from '@/components/pdf/PdfDownloadButton';
import type { AnalysisReport } from '@/types/AnalysisReport';

const {
  pdfToBlobMock,
  pdfMock,
  fontRegisterMock,
  html2canvasMock,
} = vi.hoisted(() => ({
  pdfToBlobMock: vi.fn(async () => new Blob(['pdf'])),
  pdfMock: vi.fn(() => ({ toBlob: undefined as unknown })),
  fontRegisterMock: vi.fn(),
  html2canvasMock: vi.fn(),
}));

vi.mock('@react-pdf/renderer', async () => {
  const React = await import('react');

  return {
    Document: ({ children }: { children: React.ReactNode }) => React.createElement('div', { 'data-testid': 'pdf-document' }, children),
    Page: ({ children }: { children: React.ReactNode }) => React.createElement('section', null, children),
    Text: ({ children }: { children?: React.ReactNode }) => React.createElement('span', null, children),
    View: ({ children }: { children?: React.ReactNode }) => React.createElement('div', null, children),
    Image: ({ src }: { src: string }) => React.createElement('img', { alt: 'pdf-image', src }),
    StyleSheet: { create: (styles: unknown) => styles },
    Font: { register: fontRegisterMock },
    pdf: pdfMock,
  };
});

vi.mock('html2canvas', () => ({
  default: html2canvasMock,
}));

const baseReport: AnalysisReport = {
  executiveSummary: 'Executive summary fallback',
  coreThesis: {
    headline: 'AI expansion raises execution demands',
    summary: 'Tesla is balancing margin pressure against large infrastructure investments.',
    keyPoints: ['Margins remain under pressure.', 'Capex is expected to stay elevated.'],
  },
  companyName: 'Tesla, Inc.',
  period: 'FY 2025',
  filingDate: '2026-01-29',
  keyMetrics: [
    {
      metricName: 'Revenue',
      value: '$94.8B',
      interpretation: 'Revenue declined year over year.',
      sentiment: 'negative',
    },
  ],
  businessDrivers: [
    {
      title: 'AI infrastructure build-out',
      description: 'Management expects capex above $20B in 2026.',
      impact: 'high',
    },
  ],
  riskFactors: [
    {
      category: 'Margin pressure',
      description: 'Lower pricing and fixed-cost absorption remain a risk.',
      severity: 'high',
    },
  ],
  bullCase: 'Cash flow remains resilient.',
  bearCase: 'Demand and pricing remain under pressure.',
  citations: [],
  metadata: {
    modelName: 'gpt-4o-mini',
    generatedAt: '2026-03-09T10:00:00Z',
    language: 'en',
  },
  sourceContext: {
    status: 'DEGRADED',
    message: 'SEC filing was available, but semantic grounding was not ready yet.',
  },
};

describe('PDF reporting', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pdfMock.mockImplementation(() => ({ toBlob: pdfToBlobMock }));
    pdfMock.mockClear();
    pdfToBlobMock.mockClear();
    fontRegisterMock.mockClear();
    html2canvasMock.mockReset();
    (URL as typeof URL & {
      createObjectURL?: (blob: Blob) => string;
      revokeObjectURL?: (url: string) => void;
    }).createObjectURL = vi.fn(() => 'blob:pdf-url');
    (URL as typeof URL & {
      createObjectURL?: (blob: Blob) => string;
      revokeObjectURL?: (url: string) => void;
    }).revokeObjectURL = vi.fn();
    html2canvasMock.mockResolvedValue({
      toDataURL: () => 'data:image/png;base64,chart-image',
    });
  });

  it('renders report identity metadata and degraded source context in the PDF document', () => {
    render(<AnalysisReportPDF report={baseReport} ticker="TSLA" lang="en" />);

    expect(screen.getByText('SPRING ALPHA')).toBeInTheDocument();
    expect(screen.getByText('Tesla, Inc. · FY 2025 · 2026-01-29')).toBeInTheDocument();
    expect(screen.getByText('AI expansion raises execution demands')).toBeInTheDocument();
    expect(screen.getByText('SEC filing was available, but semantic grounding was not ready yet.')).toBeInTheDocument();
    expect(screen.getByText('Status: DEGRADED')).toBeInTheDocument();
  });

  it('renders grounded citations in the PDF document when available', () => {
    render(
      <AnalysisReportPDF
        report={{
          ...baseReport,
          citations: [
            {
              section: 'MD&A',
              excerpt: 'Revenue increased due to stronger deliveries.',
              verificationStatus: 'VERIFIED',
            },
          ],
          sourceContext: {
            status: 'GROUNDED',
            message: 'Grounded in SEC evidence.',
          },
        }}
        ticker="TSLA"
        lang="en"
      />
    );

    expect(screen.getByText(/Revenue increased due to stronger deliveries\./)).toBeInTheDocument();
    expect(screen.getByText('Source: MD&A')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
    expect(screen.queryByText(/Status: DEGRADED/)).not.toBeInTheDocument();
  });

  it('captures charts and downloads a dated PDF file', async () => {
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL');
    const revokeObjectUrlSpy = vi.spyOn(URL, 'revokeObjectURL');
    const appendChildSpy = vi.spyOn(document.body, 'appendChild');
    const removeChildSpy = vi.spyOn(document.body, 'removeChild');
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    const dupontChart = document.createElement('div');
    dupontChart.id = 'chart-dupont';
    document.body.appendChild(dupontChart);

    render(<PdfDownloadButton report={baseReport} ticker="TSLA" lang="en" />);

    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }));

    await waitFor(() => {
      expect(pdfMock).toHaveBeenCalled();
      expect(pdfToBlobMock).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
    });

    const firstPdfCall = pdfMock.mock.calls[0] as unknown[] | undefined;
    expect(firstPdfCall).toBeDefined();
    const [pdfArg] = firstPdfCall!;
    expect((pdfArg as unknown as { props: { chartImages: Record<string, string> } }).props.chartImages['chart-dupont'])
      .toBe('data:image/png;base64,chart-image');
    expect(createObjectUrlSpy).toHaveBeenCalled();
    expect(revokeObjectUrlSpy).toHaveBeenCalledWith('blob:pdf-url');

    const anchor = appendChildSpy.mock.calls.find(([node]) => 'download' in (node as object))?.[0] as HTMLAnchorElement | undefined;
    expect(anchor?.download).toMatch(/^TSLA_Analysis_Report_\d{4}-\d{2}-\d{2}\.pdf$/);

    dupontChart.remove();
    createObjectUrlSpy.mockRestore();
    revokeObjectUrlSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
    clickSpy.mockRestore();
  });
});
