export type DashboardMode = 'standard' | 'financial_sector' | 'unsupported_reit';

export interface FinancialFactsSnapshot {
  currency?: string | null;
  revenue?: number | null;
  netIncome?: number | null;
  grossMargin?: number | null;
  netMargin?: number | null;
  operatingMargin?: number | null;
  earningsPerShare?: number | null;
  totalAssets?: number | null;
  totalLiabilities?: number | null;
  totalEquity?: number | null;
  revenueYoY?: number | null;
  operatingCashFlowYoY?: number | null;
  freeCashFlowYoY?: number | null;
  debtToEquityRatio?: number | null;
  returnOnEquity?: number | null;
  returnOnAssets?: number | null;
  priceToEarningsRatio?: number | null;
  priceToBookRatio?: number | null;
  marketSector?: string | null;
  marketIndustry?: string | null;
  marketSecurityType?: string | null;
  dashboardMode?: DashboardMode | null;
  dashboardMessage?: string | null;
}
