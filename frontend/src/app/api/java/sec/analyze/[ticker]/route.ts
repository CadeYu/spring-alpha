import { NextRequest } from 'next/server';

/**
 * SSE Proxy Route for stock analysis
 * 
 * Next.js rewrites have a 30s default timeout which is too short for the
 * full analysis pipeline (FMP + SEC + RAG + LLM = ~25-30s).
 * This custom route handler proxies to the backend with a 120s timeout.
 */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ ticker: string }> }
) {
    const { ticker } = await params;
    const lang = request.nextUrl.searchParams.get('lang') || 'en';
    const model = request.nextUrl.searchParams.get('model') || '';

    const baseUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8081';
    const backendUrl = `${baseUrl}/api/sec/analyze/${ticker}?lang=${lang}&model=${model}`;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120_000); // 120s timeout

        const response = await fetch(backendUrl, {
            headers: {
                'Accept': 'text/event-stream',
            },
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok || !response.body) {
            return new Response(
                JSON.stringify({ error: `Backend error: ${response.statusText}` }),
                { status: response.status, headers: { 'Content-Type': 'application/json' } }
            );
        }

        // Stream the SSE response through to the client
        return new Response(response.body, {
            status: 200,
            headers: {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache, no-transform',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
            },
        });
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error(`[SSE Proxy] Error for ${ticker}:`, message);
        return new Response(
            JSON.stringify({ error: `Proxy error: ${message}` }),
            { status: 502, headers: { 'Content-Type': 'application/json' } }
        );
    }
}

// Allow streaming responses up to 120 seconds
export const maxDuration = 120;
