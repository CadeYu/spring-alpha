import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AnalysisReportPDF } from '@/components/pdf/AnalysisReportPDF';
import { PdfDownloadButton } from '@/components/pdf/PdfDownloadButton';
import type { AnalysisReport } from '@/types/AnalysisReport';

const {
  pdfToBlobMock,
  pdfMock,
  fontRegisterMock,
} = vi.hoisted(() => ({
  pdfToBlobMock: vi.fn(async () => new Blob(['pdf-content'], { type: 'application/pdf' })),
  pdfMock: vi.fn(() => ({ toBlob: undefined as unknown })),
  fontRegisterMock: vi.fn(),
}));

vi.mock('@react-pdf/renderer', async () => {
  const React = await import('react');

  return {
    Document: ({ children }: { children: React.ReactNode }) =>
      React.createElement('div', { 'data-testid': 'pdf-document' }, children),
    Page: ({ children }: { children: React.ReactNode }) =>
      React.createElement('section', null, children),
    Text: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('span', null, children),
    View: ({ children }: { children?: React.ReactNode }) =>
      React.createElement('div', null, children),
    StyleSheet: { create: (styles: unknown) => styles },
    Font: { register: fontRegisterMock },
    pdf: pdfMock,
  };
});

const baseReport: AnalysisReport = {
  executiveSummary: 'Executive summary fallback',
  coreThesis: {
    verdict: 'mixed',
    headline: 'AI expansion raises execution demands',
    summary: 'Tesla is balancing margin pressure against large infrastructure investments.',
    whatChanged: ['AI infrastructure investment is becoming a bigger part of the operating story.'],
    drivers: [
      {
        label: 'Demand mix',
        detail: 'Revenue was $94.8B while pricing remained soft, keeping margin recovery uneven.',
      },
      {
        label: 'Cost base',
        detail: 'Free cash flow stayed positive at $2.1B, which gives Tesla room to keep investing.',
      },
    ],
    strategicBets: [
      {
        label: 'AI build-out',
        detail: 'Management is still prioritizing AI infrastructure and manufacturing capacity for the next leg.',
      },
    ],
    keyPoints: ['Margins remain under pressure.', 'Capex is expected to stay elevated.'],
    watchItems: ['Watch margin recovery.', 'Track capex cadence.'],
  },
  companyName: 'Tesla, Inc.',
  reportType: 'quarterly',
  period: 'Q4 2025',
  filingDate: '2026-01-29',
  keyMetrics: [
    {
      metricName: 'Revenue',
      value: '$94.8B',
      interpretation: 'Revenue declined year over year.',
      sentiment: 'negative',
    },
    {
      metricName: 'Free Cash Flow',
      value: '$2.1B',
      interpretation: 'Cash generation remains positive.',
      sentiment: 'neutral',
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
  citations: [
    {
      section: 'MD&A',
      excerpt: 'Revenue declined year over year due to weaker demand in core markets.',
      verificationStatus: 'VERIFIED',
    },
  ],
  metadata: {
    modelName: 'gpt-4o-mini',
    generatedAt: '2026-03-10T10:00:00Z',
    language: 'en',
  },
  sourceContext: {
    status: 'GROUNDED',
    message: 'Grounded SEC evidence was retrieved for this run.',
  },
  dupontAnalysis: {
    netProfitMargin: '0.2928',
    assetTurnover: '0.3785',
    equityMultiplier: '4.2950',
    returnOnEquity: '0.4773',
    interpretation: 'ROE remains elevated because strong profitability offsets moderate turnover.',
  },
};

const zhReport: AnalysisReport = {
  ...baseReport,
  companyName: 'Meta Platforms, Inc.',
  metadata: {
    modelName: 'gpt-4o-mini',
    generatedAt: '2026-03-11T01:05:00Z',
    language: 'zh',
  },
  coreThesis: {
    verdict: 'mixed',
    headline: 'Meta在Q4 2025实现强劲的收入和利润增长',
    summary: '在2025年第四季度，Meta Platforms, Inc.展现出强劲的财务表现，收入达到598.94亿美元，同比增长16.88%，广告与平台效率继续改善。',
    whatChanged: [
      '广告定价与展示量继续改善，Family of Apps 仍是最重要的业务引擎。',
      'AI推荐效率和Reels商业化继续推动平台变现能力提升。',
    ],
    drivers: [
      {
        label: '广告需求',
        detail: '广告收入达到1961.75亿美元，较2024年增长22.08%，继续支撑本季扩张。',
      },
      {
        label: '利润兑现',
        detail: '运营利润247.45亿美元、净利润227.68亿美元，说明成本纪律仍然有效。',
      },
    ],
    strategicBets: [
      {
        label: 'AI与基础设施',
        detail: '公司继续增加数据中心与算力投入，以支撑推荐系统、Meta AI和长期商业化。',
      },
    ],
    keyPoints: [
      '收入为598.94亿美元，同比增长16.88%，广告业务仍是核心引擎。',
      '毛利率达到81.79%，说明盈利质量仍然很强。',
      '净利润为227.7亿美元，利润扩张继续兑现。',
    ],
    watchItems: ['关注广告定价与AI投入能否继续支撑下一季增长。', '继续跟踪基础设施投入对利润率的影响。'],
  },
  keyMetrics: [
    {
      metricName: '营收',
      value: '$59.89B',
      interpretation: '广告需求和平台效率共同支撑了收入规模。',
      sentiment: 'positive',
    },
    {
      metricName: '毛利率',
      value: '81.79%',
      interpretation: '利润率维持高位，显示出强定价能力。',
      sentiment: 'positive',
    },
    {
      metricName: '净利润',
      value: '$22.77B',
      interpretation: '净利润继续扩张，盈利兑现度较高。',
      sentiment: 'positive',
    },
    {
      metricName: '营收同比增长',
      value: '16.88%',
      interpretation: '同比增速说明增长动能仍然稳健。',
      sentiment: 'positive',
    },
  ],
  bullCase: '广告效率持续改善，AI 投入有望继续放大商业化。',
  bearCase: '高基数下增速回落会压缩估值想象空间。',
};

const fallbackReport: AnalysisReport = {
  ...baseReport,
  coreThesis: {
    verdict: 'positive',
    headline: 'Core demand remains intact despite a heavier investment cycle',
    summary: 'The business is still being driven by execution in the core franchise, while capex remains elevated.',
  },
  businessSignals: {
    segmentPerformance: [
      {
        title: 'Core auto demand',
        summary: 'Automotive revenue held up better than feared even as pricing stayed promotional.',
      },
    ],
    managementFocus: [
      {
        title: 'Execution',
        summary: 'Management is focused on margin discipline and manufacturing throughput.',
      },
    ],
    strategicMoves: [
      {
        title: 'AI capacity',
        summary: 'The company is still building AI and compute capacity ahead of future product launches.',
      },
    ],
    riskSignals: [
      {
        title: 'Next quarter',
        summary: 'Watch whether pricing pressure eases before the next print.',
      },
    ],
  },
};

const tightReport: AnalysisReport = {
  ...zhReport,
  coreThesis: {
    verdict: 'mixed',
    headline: 'Meta在Q4 2025实现强劲增长，但市场真正关心的是广告效率、AI投入和利润兑现能否继续同时成立',
    summary: '本季收入598.94亿美元，同比增长16.88%。更重要的是广告收入1961.75亿美元，同比增长22.08%，而运营利润247.45亿美元、净利润227.68亿美元，说明核心广告机器仍在覆盖AI与基础设施投入，不过后续还要继续跟踪投入节奏、广告定价和商业化兑现之间的平衡。',
    whatChanged: [
      '广告收入达到1961.75亿美元，同比增长22.08%，Family of Apps 继续主导扩张，广告引擎仍是最重要的增长来源。',
      '运营利润247.45亿美元、净利润227.68亿美元，说明利润兑现并未被投入节奏打断，盈利韧性仍然存在。',
    ],
    drivers: [
      {
        label: '广告需求',
        detail: '广告收入达到1961.75亿美元，较2024年增长22.08%，继续支撑本季扩张，同时也说明广告定价和转化效率仍在改善。',
      },
      {
        label: '利润兑现',
        detail: '运营利润247.45亿美元、净利润227.68亿美元，说明成本纪律仍然有效，且大规模资本开支尚未完全侵蚀盈利能力。',
      },
    ],
    strategicBets: [
      {
        label: 'AI与基础设施',
        detail: '公司继续增加数据中心与算力投入，以支撑推荐系统、Meta AI和长期商业化，同时为后续产品节奏和广告效率优化提供底层保障。',
      },
      {
        label: '商业化延展',
        detail: '管理层仍在押注Reels、消息和AI助手的长期变现空间，并希望把用户时长和商业转化进一步打通。',
      },
    ],
    watchItems: [
      '关注广告定价与AI投入能否继续支撑下一季增长，并观察高基数下广告需求是否出现放缓迹象。',
      '继续跟踪基础设施投入对利润率的影响，以及AI产品商业化能否开始贡献更直接的收入增量。',
    ],
  },
  citations: [
    {
      section: 'MD&A',
      excerpt: 'Ad revenue continued to benefit from stronger advertiser demand and improved ad performance.',
      excerptZh: '广告收入继续受益于更强的广告主需求和更好的广告表现，这一趋势仍在延续。',
      verificationStatus: 'VERIFIED',
    },
  ],
};

describe('PDF reporting', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pdfMock.mockImplementation(() => ({ toBlob: pdfToBlobMock }));
    pdfMock.mockClear();
    pdfToBlobMock.mockClear();
    fontRegisterMock.mockClear();
  });

  it('renders the compact shareable PDF layout', () => {
    render(<AnalysisReportPDF report={baseReport} ticker="TSLA" lang="en" />);

    expect(screen.getByText('AI Earnings Poster')).toBeInTheDocument();
    expect(screen.getByText('Tesla, Inc.')).toBeInTheDocument();
    expect(screen.getByText('AI expansion raises execution demands')).toBeInTheDocument();
    expect(screen.getByText('Four questions that frame the quarter')).toBeInTheDocument();
    expect(screen.getByText('What Changed')).toBeInTheDocument();
    expect(screen.getByText('What Drove It')).toBeInTheDocument();
    expect(screen.getByText('What Is The Bet')).toBeInTheDocument();
    expect(screen.getByText('What To Watch')).toBeInTheDocument();
    expect(screen.getByText('Bull case')).toBeInTheDocument();
    expect(screen.getByText('Source check')).toBeInTheDocument();
    expect(screen.getAllByText('$94.8B').length).toBeGreaterThan(0);
    expect(screen.getByText('Demand mix')).toBeInTheDocument();
    expect(screen.getByText('AI build-out')).toBeInTheDocument();
    expect(screen.getByText('Revenue declined year over year due to weaker demand in core markets.')).toBeInTheDocument();
  });

  it('renders chinese poster metrics and four-question content without dropping the headline numbers', () => {
    render(<AnalysisReportPDF report={zhReport} ticker="META" lang="zh" />);

    expect(screen.getByText('Meta在Q4 2025实现强劲的收入和利润增长')).toBeInTheDocument();
    expect(screen.getAllByText('16.88%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('$59.89B').length).toBeGreaterThan(0);
    expect(screen.getByText('季度营收规模')).toBeInTheDocument();
    expect(screen.getByText('四个最值得先看的问题')).toBeInTheDocument();
    expect(screen.getByText('本季发生了什么')).toBeInTheDocument();
    expect(screen.getByText('核心驱动因素')).toBeInTheDocument();
    expect(screen.getByText('公司在押注什么')).toBeInTheDocument();
    expect(screen.getByText('后续跟踪什么')).toBeInTheDocument();
    expect(screen.getByText('广告需求')).toBeInTheDocument();
    expect(screen.getByText('AI与基础设施')).toBeInTheDocument();
    expect(screen.queryAllByText('--')).toHaveLength(0);
  });

  it('falls back to business signals when structured question fields are missing', () => {
    render(<AnalysisReportPDF report={fallbackReport} ticker="TSLA" lang="en" />);

    expect(screen.getByText('Core auto demand')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('AI capacity')).toBeInTheDocument();
    expect(screen.getByText('Next quarter: Watch whether pricing pressure eases before the next print.')).toBeInTheDocument();
  });

  it('switches to tighter single-page content budgeting for longer reports', () => {
    render(<AnalysisReportPDF report={tightReport} ticker="META" lang="zh" />);

    expect(screen.getByText('广告需求')).toBeInTheDocument();
    expect(screen.getByText('AI与基础设施')).toBeInTheDocument();
    expect(screen.queryByText('利润兑现')).not.toBeInTheDocument();
    expect(screen.queryByText('商业化延展')).not.toBeInTheDocument();
  });

  it('downloads a generated PDF blob instead of opening a print window', async () => {
    const originalCreateObjectUrl = URL.createObjectURL;
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(() => 'blob:pdf'),
    });

    const createObjectUrlSpy = vi.mocked(URL.createObjectURL);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild');
    const originalCreateElement = document.createElement.bind(document);
    const anchorClickSpy = vi.fn();
    const anchorRemoveSpy = vi.fn();

    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      const element = originalCreateElement(tagName);
      if (tagName.toLowerCase() === 'a') {
        Object.defineProperty(element, 'click', {
          configurable: true,
          value: anchorClickSpy,
        });
        Object.defineProperty(element, 'remove', {
          configurable: true,
          value: anchorRemoveSpy,
        });
      }
      return element;
    }) as typeof document.createElement);

    render(<PdfDownloadButton report={baseReport} ticker="TSLA" lang="en" />);

    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }));

    await waitFor(() => {
      expect(pdfMock).toHaveBeenCalledTimes(1);
      expect(pdfToBlobMock).toHaveBeenCalledTimes(1);
      expect(anchorClickSpy).toHaveBeenCalledTimes(1);
    });

    const appendedAnchor = appendChildSpy.mock.calls.find(
      ([node]) => node instanceof HTMLAnchorElement
    )?.[0] as HTMLAnchorElement | undefined;

    expect(appendedAnchor?.download).toMatch(/^TSLA_AI_Analysis_Report_\d{4}-\d{2}-\d{2}\.pdf$/);
    expect(appendedAnchor?.href).toBe('blob:pdf');
    expect(createObjectUrlSpy).toHaveBeenCalledTimes(1);
    expect(anchorRemoveSpy).toHaveBeenCalledTimes(1);

    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: originalCreateObjectUrl,
    });
  });

  it('surfaces a direct error if blob generation fails', async () => {
    pdfToBlobMock.mockRejectedValueOnce(new Error('boom'));

    render(<PdfDownloadButton report={baseReport} ticker="TSLA" lang="en" />);

    fireEvent.click(screen.getByRole('button', { name: /download pdf/i }));

    await waitFor(() => {
      expect(screen.getByText('PDF export failed: boom')).toBeInTheDocument();
    });
  });
});
