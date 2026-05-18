import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";
import { GET, maxDuration } from "./route";

describe("analysis SSE bridge", () => {
  it("allows long-running live LLM research streams", () => {
    expect(maxDuration).toBe(240);
  });

  it("rejects unsupported task types before calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=freeform_prompt",
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({
      error: "Unsupported taskType: freeform_prompt",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the selected BYOK provider key to the backend", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data:{}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn(async () => new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
        {
          headers: { "X-Provider-API-Key": "sk-test-123" },
        },
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe(
      "text/event-stream; charset=utf-8",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining(
        "http://127.0.0.1:8082/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
      ),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Provider-API-Key": "sk-test-123",
        }),
      }),
    );
  });

  it("forwards anonymous visitor context when no BYOK key is present", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data:{}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn(async () => new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const visitorId = "2cc57d20-ebd4-49bd-b53d-2c935bd9e01c";
    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
        {
          headers: { cookie: `spring-alpha-visitor-id=${visitorId}` },
        },
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/sec/analyze/AAPL"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Auth-Mode": "anonymous",
          "X-Visitor-Id": visitorId,
        }),
      }),
    );
  });
});
