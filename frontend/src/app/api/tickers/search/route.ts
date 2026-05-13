import { NextRequest } from "next/server";

const SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json";
const SEC_USER_AGENT = "SpringAlpha/1.0 ticker-search contact@springalpha.local";
const DEFAULT_LIMIT = 8;
const MAX_LIMIT = 12;

type SecCompanyTickerRecord = {
  cik_str?: number;
  ticker?: string;
  title?: string;
};

type TickerSuggestion = {
  ticker: string;
  companyName: string;
};

let cachedCatalog: TickerSuggestion[] | null = null;

export async function GET(request: NextRequest) {
  const query = normalizeQuery(request.nextUrl.searchParams.get("q") ?? "");
  const limit = resolveLimit(request.nextUrl.searchParams.get("limit"));

  if (query.length < 2) {
    return Response.json({ suggestions: [] });
  }

  try {
    const catalog = await loadTickerCatalog();
    return Response.json({
      suggestions: searchTickerCatalog(catalog, query, limit),
    });
  } catch (error) {
    console.error("Ticker search failed:", error);
    return Response.json({ suggestions: [] }, { status: 200 });
  }
}

async function loadTickerCatalog(): Promise<TickerSuggestion[]> {
  if (cachedCatalog) return cachedCatalog;

  const response = await fetch(SEC_COMPANY_TICKERS_URL, {
    headers: {
      Accept: "application/json",
      "User-Agent": SEC_USER_AGENT,
    },
    next: { revalidate: 24 * 60 * 60 },
  });

  if (!response.ok) {
    throw new Error(`SEC ticker catalog request failed: ${response.status}`);
  }

  const payload = (await response.json()) as Record<string, SecCompanyTickerRecord>;
  cachedCatalog = Object.values(payload)
    .map((record) => ({
      ticker: normalizeTicker(record.ticker ?? ""),
      companyName: (record.title ?? "").trim(),
    }))
    .filter((record) => record.ticker && record.companyName);

  return cachedCatalog;
}

function searchTickerCatalog(
  catalog: TickerSuggestion[],
  query: string,
  limit: number,
): TickerSuggestion[] {
  const normalizedQuery = normalizeQuery(query);

  return catalog
    .filter(
      (record) =>
        record.ticker.includes(normalizedQuery) ||
        normalizeQuery(record.companyName).includes(normalizedQuery),
    )
    .sort((left, right) => {
      const leftScore = rankSuggestion(left, normalizedQuery);
      const rightScore = rankSuggestion(right, normalizedQuery);
      if (leftScore !== rightScore) return leftScore - rightScore;
      return left.ticker.localeCompare(right.ticker);
    })
    .slice(0, limit);
}

function rankSuggestion(record: TickerSuggestion, query: string): number {
  if (record.ticker === query) return 0;
  if (record.ticker.startsWith(query)) return 1;
  if (normalizeQuery(record.companyName).startsWith(query)) return 2;
  if (record.ticker.includes(query)) return 3;
  return 4;
}

function resolveLimit(rawLimit: string | null): number {
  const parsed = Number(rawLimit);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_LIMIT;
  return Math.min(Math.floor(parsed), MAX_LIMIT);
}

function normalizeTicker(value: string): string {
  return value.trim().toUpperCase();
}

function normalizeQuery(value: string): string {
  return value.trim().toUpperCase();
}
