import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  FinancialHealthRadar,
  buildRadarData,
  computeOverallScore,
  hasMarketPricingData,
  scoreMarketPricing,
} from './financial-health-radar';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('FinancialHealthRadar scoring', () => {
  it('keeps strong mature fundamentals from being unfairly dragged down by market pricing', () => {
    const radarData = buildRadarData(
      {
        grossMargin: 0.4691,
        operatingMargin: 0.315,
        netMargin: 0.2692,
        revenueYoY: 0.0643,
        operatingCashFlowYoY: -0.0573,
        freeCashFlowYoY: 0.021,
        debtToEquityRatio: 1.06,
        returnOnEquity: 1.52,
        returnOnAssets: 0.31,
        priceToEarningsRatio: 32,
        priceToBookRatio: 45,
      },
      'zh',
    );

    const scoreByKey = Object.fromEntries(radarData.map((item) => [item.key, item.score]));
    const overallScore = computeOverallScore(radarData);

    expect(scoreByKey.profitability).toBeGreaterThanOrEqual(80);
    expect(scoreByKey.efficiency).toBeGreaterThanOrEqual(85);
    expect(scoreByKey.growth).toBeGreaterThanOrEqual(60);
    expect(scoreByKey.pricing).toBeLessThan(scoreByKey.profitability);
    expect(overallScore).toBeGreaterThanOrEqual(70);
  });

  it('treats modest positive growth as healthy instead of mediocre for mature companies', () => {
    const radarData = buildRadarData(
      {
        revenueYoY: 0.03,
        operatingCashFlowYoY: 0.02,
        freeCashFlowYoY: 0.01,
      },
      'en',
    );

    const scoreByKey = Object.fromEntries(radarData.map((item) => [item.key, item.score]));

    expect(scoreByKey.growth).toBeGreaterThanOrEqual(55);
    expect(scoreByKey.cashFlow).toBeGreaterThanOrEqual(55);
  });

  it('hides market pricing when no supplemental valuation data is available', () => {
    const facts = {
      grossMargin: 0.4,
      operatingMargin: 0.22,
      netMargin: 0.18,
      revenueYoY: 0.08,
      operatingCashFlowYoY: 0.09,
      freeCashFlowYoY: 0.07,
      debtToEquityRatio: 0.7,
      returnOnEquity: 0.24,
      returnOnAssets: 0.11,
    };

    const radarData = buildRadarData(facts, 'en');

    expect(hasMarketPricingData(facts)).toBe(false);
    expect(scoreMarketPricing(facts)).toBeNull();
    expect(radarData.some((item) => item.key === 'pricing')).toBe(false);
  });

  it('ignores non-positive valuation and leverage inputs instead of forcing scores', () => {
    const facts = {
      grossMargin: 0.4,
      operatingMargin: 0.22,
      netMargin: 0.18,
      revenueYoY: 0.08,
      debtToEquityRatio: -24.58,
      returnOnEquity: 0.24,
      returnOnAssets: 0.11,
      priceToEarningsRatio: -3,
      priceToBookRatio: 0,
    };

    const radarData = buildRadarData(facts, 'en');

    expect(hasMarketPricingData(facts)).toBe(false);
    expect(scoreMarketPricing(facts)).toBeNull();
    expect(radarData.some((item) => item.key === 'pricing')).toBe(false);
    expect(radarData.some((item) => item.key === 'leverage')).toBe(false);
  });

  it('renders a financial-sector snapshot for bank-style tickers', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: 'financial_sector',
        dashboardMessage: 'Financial sector mode is active.',
        currency: 'USD',
        netMargin: 0.31,
        returnOnEquity: 0.04,
        returnOnAssets: 0.0032,
        earningsPerShare: 5.07,
        priceToEarningsRatio: 14.1,
        priceToBookRatio: 2.22,
        totalAssets: 4560205000000,
        totalEquity: 360212000000,
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <FinancialHealthRadar
        ticker="JPM"
        lang="en"
        apiBase="/api/java"
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/java/financial/JPM');
    });

    expect(await screen.findByText('Financial Sector Mode')).toBeInTheDocument();
    expect(screen.getByText('Financial sector mode is active.')).toBeInTheDocument();
    expect(screen.getByText('🏦 Financial Sector Snapshot')).toBeInTheDocument();
    expect(screen.getByText('ROE')).toBeInTheDocument();
    expect(screen.getByText('Total Assets')).toBeInTheDocument();
  });

  it('renders an unsupported notice for REIT tickers', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: 'unsupported_reit',
        dashboardMessage: 'This ticker is categorized as a REIT / trust-like issuer.',
      }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    render(
      <FinancialHealthRadar
        ticker="PLD"
        lang="en"
        apiBase="/api/java"
      />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/java/financial/PLD');
    });

    expect(await screen.findByText('Unsupported Security Type')).toBeInTheDocument();
    expect(screen.getByText('This ticker is categorized as a REIT / trust-like issuer.')).toBeInTheDocument();
  });
});
