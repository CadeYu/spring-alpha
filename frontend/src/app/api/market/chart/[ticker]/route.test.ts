import { describe, expect, it, vi, beforeEach } from "vitest";
import { GET } from "./route";

function fetchUrl(fetchMock: ReturnType<typeof vi.fn>, index = 0) {
  const call = fetchMock.mock.calls.at(index);
  if (!call) throw new Error(`Missing fetch call at index ${index}`);
  const [input] = call as [string | URL | Request, RequestInit?];
  return new URL(input instanceof Request ? input.url : input.toString());
}

describe("market chart route", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("requests all-time daily data with period bounds to avoid Yahoo range=max downsampling", async () => {
    const timestamps = Array.from(
      { length: 120 },
      (_, index) => 1778198400 + index * 86400,
    );
    const fetchMock = vi.fn(async () =>
      Response.json({
        chart: {
          result: [
            {
              timestamp: timestamps,
              indicators: {
                quote: [
                  {
                    open: timestamps.map((_, index) => 100 + index),
                    high: timestamps.map((_, index) => 112 + index),
                    low: timestamps.map((_, index) => 98 + index),
                    close: timestamps.map((_, index) => 108 + index),
                    volume: timestamps.map((_, index) => 123456 + index),
                  },
                ],
              },
            },
          ],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(new Request("http://localhost"), {
      params: Promise.resolve({ ticker: "aapl" }),
    });

    expect(response.status).toBe(200);
    const payload = (await response.json()) as {
      candles: Array<{
        date: string;
        open: number;
        high: number;
        low: number;
        close: number;
        volume: number;
      }>;
    };
    expect(payload.candles).toHaveLength(120);
    expect(payload.candles[0]).toEqual({
      date: "2026-05-08",
      open: 100,
      high: 112,
      low: 98,
      close: 108,
      volume: 123456,
    });
    expect(payload.candles[119]).toEqual({
      date: "2026-09-04",
      open: 219,
      high: 231,
      low: 217,
      close: 227,
      volume: 123575,
    });
    const calledUrl = fetchUrl(fetchMock);
    expect(calledUrl.origin + calledUrl.pathname).toBe(
      "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
    );
    expect(calledUrl.searchParams.get("interval")).toBe("1d");
    expect(calledUrl.searchParams.get("range")).toBeNull();
    expect(Number(calledUrl.searchParams.get("period1"))).toBeLessThan(
      Number(calledUrl.searchParams.get("period2")),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Accept: "application/json" }),
      }),
    );
  });

  it("drops incomplete Yahoo rows and degrades to an empty chart on upstream failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          chart: {
            result: [
              {
                timestamp: [1778198400],
                indicators: {
                  quote: [
                    {
                      open: [100],
                      high: [null],
                      low: [98],
                      close: [108],
                      volume: [123456],
                    },
                  ],
                },
              },
            ],
          },
        }),
      ),
    );

    const incompleteResponse = await GET(new Request("http://localhost"), {
      params: Promise.resolve({ ticker: "MSFT" }),
    });

    expect(await incompleteResponse.json()).toEqual({ candles: [] });

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("Bad gateway", { status: 502 })),
    );

    const failedResponse = await GET(new Request("http://localhost"), {
      params: Promise.resolve({ ticker: "MSFT" }),
    });

    expect(failedResponse.status).toBe(200);
    expect(await failedResponse.json()).toEqual({ candles: [] });
  });

  it("requests weekly and monthly data with period bounds from the query parameter", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({
        chart: {
          result: [
            {
              timestamp: [1778198400],
              indicators: {
                quote: [
                  {
                    open: [100],
                    high: [112],
                    low: [98],
                    close: [108],
                    volume: [123456],
                  },
                ],
              },
            },
          ],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await GET(new Request("http://localhost/api/market/chart/AAPL?interval=1wk"), {
      params: Promise.resolve({ ticker: "AAPL" }),
    });
    await GET(new Request("http://localhost/api/market/chart/AAPL?interval=1mo"), {
      params: Promise.resolve({ ticker: "AAPL" }),
    });

    const weeklyUrl = fetchUrl(fetchMock, 0);
    const monthlyUrl = fetchUrl(fetchMock, 1);
    expect(weeklyUrl.searchParams.get("interval")).toBe("1wk");
    expect(monthlyUrl.searchParams.get("interval")).toBe("1mo");
    expect(weeklyUrl.searchParams.get("range")).toBeNull();
    expect(monthlyUrl.searchParams.get("range")).toBeNull();
    expect(Number(weeklyUrl.searchParams.get("period1"))).toBeLessThan(
      Number(weeklyUrl.searchParams.get("period2")),
    );
    expect(Number(monthlyUrl.searchParams.get("period1"))).toBeLessThan(
      Number(monthlyUrl.searchParams.get("period2")),
    );
  });

  it("builds yearly candles from Yahoo monthly candles", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          chart: {
            result: [
              {
                timestamp: [1704067200, 1706745600, 1735689600],
                indicators: {
                  quote: [
                    {
                      open: [100, 110, 200],
                      high: [120, 130, 240],
                      low: [90, 95, 180],
                      close: [115, 125, 230],
                      volume: [10, 20, 30],
                    },
                  ],
                },
              },
            ],
          },
        }),
      ),
    );

    const response = await GET(
      new Request("http://localhost/api/market/chart/AAPL?interval=1y"),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(await response.json()).toEqual({
      candles: [
        {
          date: "2024-01-01",
          open: 100,
          high: 130,
          low: 90,
          close: 125,
          volume: 30,
        },
        {
          date: "2025-01-01",
          open: 200,
          high: 240,
          low: 180,
          close: 230,
          volume: 30,
        },
      ],
    });
  });
});
