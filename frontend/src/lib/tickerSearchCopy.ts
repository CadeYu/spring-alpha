export type TickerSearchLocale = "zh" | "en";

export const tickerSearchPlaceholder: Record<TickerSearchLocale, string> = {
  zh: "输入股票代码 (如 AAPL, MSFT)",
  en: "Enter Ticker (e.g., AAPL, MSFT, TSLA)",
};

export const tickerSearchButtonLabel: Record<TickerSearchLocale, string> = {
  zh: "开始分析",
  en: "Analyze ticker",
};
