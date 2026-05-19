import { NextRequest } from 'next/server';
import { randomUUID } from 'crypto';
import { isResearchTaskId } from '@/lib/researchTasks';
import { visitorCookieName } from '@/lib/auth';

const ANALYSIS_PROXY_TIMEOUT_MS = 240_000;
const VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

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
    const llmModel = request.nextUrl.searchParams.get('llmModel') || '';
    const taskType = request.nextUrl.searchParams.get('taskType') || '';
    const providerApiKey =
        request.headers.get('x-provider-api-key') ||
        request.headers.get('x-openai-api-key');
    const visitorId = request.cookies.get(visitorCookieName)?.value || randomUUID();
    const authMode = request.headers.get('x-auth-mode') || 'anonymous';
    const trialRunId = request.headers.get('x-trial-run-id') || '';
    const clientIpHash = await hashClientIp(request);

    const baseUrl = process.env.BACKEND_URL || 'http://127.0.0.1:8082';
    const backendParams = new URLSearchParams({ lang, model });
    if (llmModel) {
        backendParams.set('llmModel', llmModel);
    }
    if (taskType) {
        if (!isResearchTaskId(taskType)) {
            return new Response(
                JSON.stringify({ error: `Unsupported taskType: ${taskType}` }),
                { status: 400, headers: { 'Content-Type': 'application/json' } }
            );
        }
        backendParams.set('taskType', taskType);
    }
    const backendUrl = `${baseUrl}/api/sec/analyze/${ticker}?${backendParams.toString()}`;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), ANALYSIS_PROXY_TIMEOUT_MS);
        request.signal.addEventListener('abort', () => controller.abort(), { once: true });

        const response = await fetch(backendUrl, {
            headers: {
                'Accept': 'text/event-stream',
                'X-Auth-Mode': authMode,
                'X-Visitor-Id': visitorId,
                ...(trialRunId ? { 'X-Trial-Run-Id': trialRunId } : {}),
                ...(clientIpHash ? { 'X-Client-IP-Hash': clientIpHash } : {}),
                ...(providerApiKey ? { 'X-Provider-API-Key': providerApiKey } : {}),
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

        const proxiedResponse = new Response(stream, {
            status: 200,
            headers: {
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Cache-Control': 'no-cache, no-transform',
                'X-Accel-Buffering': 'no',
            },
        });
        proxiedResponse.headers.append(
            'Set-Cookie',
            `${visitorCookieName}=${visitorId}; Path=/; Max-Age=${VISITOR_COOKIE_MAX_AGE}; SameSite=Lax; HttpOnly`
        );
        return proxiedResponse;
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        console.error(`[SSE Proxy] Error for ${ticker}:`, message);
        return new Response(
            JSON.stringify({ error: `Proxy error: ${message}` }),
            { status: 502, headers: { 'Content-Type': 'application/json' } }
        );
    }
}

// Allow long-running live LLM research streams.
export const maxDuration = 240;

async function hashClientIp(request: NextRequest) {
    const forwardedFor = request.headers.get('x-forwarded-for') || '';
    const clientIp = forwardedFor.split(',')[0]?.trim();
    if (!clientIp) {
        return null;
    }

    const digest = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(clientIp),
    );
    return Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, '0'))
        .join('');
}
