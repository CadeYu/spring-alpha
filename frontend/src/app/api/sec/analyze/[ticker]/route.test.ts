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

  it("forwards authenticated provider keys to the backend without putting them in the URL", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data:{}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn(async (..._args: Parameters<typeof fetch>) =>
      new Response(stream, { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
        {
          headers: {
            "X-Auth-Mode": "authenticated",
            "X-Provider-API-Key": "test-provider-key-123",
          },
        },
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [backendUrl, requestInit] = fetchMock.mock.calls[0];
    expect(String(backendUrl)).not.toContain("test-provider-key-123");
    expect(requestInit).toEqual(
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Auth-Mode": "authenticated",
          "X-Provider-API-Key": "test-provider-key-123",
        }),
      }),
    );
  });

  it("uses the production backend url on Vercel when no explicit backend url is configured", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data:{}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi.fn(async () => new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VERCEL", "1");
    vi.stubEnv("BACKEND_URL", "");

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    const [backendUrl] = fetchMock.mock.calls[0];
    const parsedBackendUrl = new URL(String(backendUrl));
    expect(parsedBackendUrl.origin).toBe("http://45.77.171.32");
    expect(parsedBackendUrl.pathname).toBe("/api/sec/analyze/AAPL");
    expect(parsedBackendUrl.searchParams.get("lang")).toBe("en");
    expect(parsedBackendUrl.searchParams.get("model")).toBe("siliconflow");
    expect(parsedBackendUrl.searchParams.get("taskType")).toBe(
      "latest_earnings_readout",
    );
    expect(parsedBackendUrl.searchParams.get("ragMode")).toBe("local");
  });

  it("forwards the selected provider model to the backend", async () => {
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
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=deepseek-ai%2Fdeepseek-v4-flash&taskType=latest_earnings_readout",
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("llmModel=deepseek-ai%2Fdeepseek-v4-flash"),
      expect.anything(),
    );
  });

  it("forwards the selected RAG retrieval mode to the backend", async () => {
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
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout&ragMode=qdrant",
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("ragMode=qdrant"),
      expect.anything(),
    );
  });

  it("rejects unsupported RAG retrieval modes before calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout&ragMode=remote",
      ),
      { params: Promise.resolve({ ticker: "AAPL" }) },
    );

    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({
      error: "Unsupported ragMode: remote",
    });
    expect(fetchMock).not.toHaveBeenCalled();
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
    const trialRunId = "7f2819ce-042c-4a54-ac27-74294d2f9ca3";
    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
        {
          headers: {
            cookie: `spring-alpha-visitor-id=${visitorId}`,
            "X-Trial-Run-Id": trialRunId,
            "X-Forwarded-For": "203.0.113.9",
          },
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
          "X-Trial-Run-Id": trialRunId,
          "X-Client-IP-Hash": expect.any(String),
        }),
      }),
    );
  });

  it("retries transient backend fetch failures before the SSE stream starts", async () => {
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode("data:{}\n\n"));
        controller.close();
      },
    });
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(new Response(stream, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(
      new NextRequest(
        "http://localhost/api/sec/analyze/NKE?lang=zh&model=siliconflow&taskType=business_driver_deep_dive",
      ),
      { params: Promise.resolve({ ticker: "NKE" }) },
    );

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toEqual(fetchMock.mock.calls[0][0]);
  });
});
