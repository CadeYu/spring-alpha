type YahooChartResponse = {
  chart?: {
    result?: Array<{
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          open?: Array<number | null>;
          high?: Array<number | null>;
          low?: Array<number | null>;
          close?: Array<number | null>;
          volume?: Array<number | null>;
        }>;
      };
    }>;
  };
};

type MarketChartInterval = "1d" | "1wk" | "1mo" | "1y";

type MarketChartCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
};

const YAHOO_CHART_BASE_URL =
  "https://query1.finance.yahoo.com/v8/finance/chart";
const DEFAULT_START_DATE_UTC = Date.UTC(1970, 0, 1) / 1000;

export async function GET(
  request: Request,
  { params }: { params: Promise<{ ticker: string }> },
) {
  const { ticker } = await params;
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!normalizedTicker) {
    return Response.json({ candles: [] }, { status: 400 });
  }

  const requestedInterval = new URL(request.url).searchParams.get("interval");
  const interval = resolveInterval(requestedInterval);
  const yahooInterval = interval === "1y" ? "1mo" : interval;
  const yahooUrl = buildYahooChartUrl(normalizedTicker, yahooInterval);

  try {
    const response = await fetch(yahooUrl, {
      headers: {
        Accept: "application/json",
        "User-Agent": "SpringAlpha/1.0 market-chart contact@springalpha.local",
      },
      next: { revalidate: 15 * 60 },
    });

    if (!response.ok) {
      return Response.json({ candles: [] }, { status: 200 });
    }

    const payload = (await response.json()) as YahooChartResponse;
    const result = payload.chart?.result?.[0];
    const timestamps = result?.timestamp ?? [];
    const quote = result?.indicators?.quote?.[0];
    const candles = timestamps
      .map((timestamp, index) => {
        const open = quote?.open?.[index];
        const high = quote?.high?.[index];
        const low = quote?.low?.[index];
        const close = quote?.close?.[index];
        if (
          !isFiniteNumber(open) ||
          !isFiniteNumber(high) ||
          !isFiniteNumber(low) ||
          !isFiniteNumber(close)
        ) {
          return null;
        }
        return {
          date: new Date(timestamp * 1000).toISOString().slice(0, 10),
          open,
          high,
          low,
          close,
          volume: quote?.volume?.[index] ?? null,
        };
      })
      .filter((candle): candle is NonNullable<typeof candle> => candle !== null);

    return Response.json({
      candles: interval === "1y" ? aggregateYearlyCandles(candles) : candles,
    });
  } catch (error) {
    console.error("Market chart fetch failed:", error);
    return Response.json({ candles: [] }, { status: 200 });
  }
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function resolveInterval(interval: string | null): MarketChartInterval {
  if (
    interval === "1d" ||
    interval === "1wk" ||
    interval === "1mo" ||
    interval === "1y"
  ) {
    return interval;
  }
  return "1d";
}

function buildYahooChartUrl(ticker: string, interval: Exclude<MarketChartInterval, "1y">) {
  const url = new URL(`${YAHOO_CHART_BASE_URL}/${encodeURIComponent(ticker)}`);
  url.searchParams.set("period1", String(DEFAULT_START_DATE_UTC));
  url.searchParams.set("period2", String(Math.floor(Date.now() / 1000)));
  url.searchParams.set("interval", interval);
  return url.toString();
}

function aggregateYearlyCandles(
  candles: MarketChartCandle[],
): MarketChartCandle[] {
  const yearlyCandles = new Map<string, MarketChartCandle>();

  for (const candle of candles) {
    const year = candle.date.slice(0, 4);
    const existing = yearlyCandles.get(year);
    if (!existing) {
      yearlyCandles.set(year, {
        date: `${year}-01-01`,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
      });
      continue;
    }

    yearlyCandles.set(year, {
      ...existing,
      high: Math.max(existing.high, candle.high),
      low: Math.min(existing.low, candle.low),
      close: candle.close,
      volume:
        existing.volume === null && candle.volume === null
          ? null
          : (existing.volume ?? 0) + (candle.volume ?? 0),
    });
  }

  return Array.from(yearlyCandles.values());
}
