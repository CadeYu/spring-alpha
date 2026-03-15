import { NextRequest } from 'next/server';

/**
 * SSE bridge route for stock analysis.
 *
 * Keep this outside `/api/java/*` so it is not intercepted by the global
 * rewrite proxy used for non-streaming backend routes in local development.
 */
export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ ticker: string }> }
) {
    const { ticker } = await params;
    const lang = request.nextUrl.searchParams.get('lang') || 'en';
    const model = request.nextUrl.searchParams.get('model') || '';
    const openAiApiKey = request.headers.get('x-openai-api-key');

    const baseUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8081';
    const backendUrl = `${baseUrl}/api/sec/analyze/${ticker}?lang=${lang}&model=${model}`;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120_000); // 120s timeout
        request.signal.addEventListener('abort', () => controller.abort(), { once: true });

        const response = await fetch(backendUrl, {
            headers: {
                'Accept': 'text/event-stream',
                ...(openAiApiKey ? { 'X-OpenAI-API-Key': openAiApiKey } : {}),
            },
            signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (!response.ok || !response.body) {
            const errorText = await response.text();
            return new Response(
                errorText || JSON.stringify({ error: `Backend error: ${response.statusText}` }),
                {
                    status: response.status,
                    headers: { 'Content-Type': response.headers.get('content-type') || 'application/json' },
                }
            );
        }

        const upstream = response.body;
        const stream = new ReadableStream<Uint8Array>({
            async start(streamController) {
                const reader = upstream.getReader();
                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) {
                            break;
                        }
                        if (value) {
                            streamController.enqueue(value);
                        }
                    }
                    streamController.close();
                } catch (error) {
                    streamController.error(error);
                } finally {
                    clearTimeout(timeoutId);
                    reader.releaseLock();
                }
            },
            cancel() {
                controller.abort();
                clearTimeout(timeoutId);
            },
        });

        return new Response(stream, {
            status: 200,
            headers: {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache, no-transform',
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
