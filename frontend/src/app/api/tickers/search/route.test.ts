import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

describe("ticker search route", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("searches the SEC company ticker catalog by ticker and company name", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          0: { cik_str: 320193, ticker: "AAPL", title: "Apple Inc." },
          1: { cik_str: 59478, ticker: "LLY", title: "Eli Lilly and Company" },
          2: { cik_str: 1067983, ticker: "BRK-B", title: "Berkshire Hathaway Inc." },
        }),
      ),
    );

    const response = await GET(
      new NextRequest("http://localhost/api/tickers/search?q=lil"),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      suggestions: [
        {
          ticker: "LLY",
          companyName: "Eli Lilly and Company",
        },
      ],
    });
  });

  it("supports class-share tickers returned by the SEC catalog", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({
          0: { cik_str: 1067983, ticker: "BRK-B", title: "Berkshire Hathaway Inc." },
        }),
      ),
    );

    const response = await GET(
      new NextRequest("http://localhost/api/tickers/search?q=brk"),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      suggestions: [
        {
          ticker: "BRK-B",
          companyName: "Berkshire Hathaway Inc.",
        },
      ],
    });
  });
});
