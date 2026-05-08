package com.springalpha.backend.service.research;

import com.springalpha.backend.financial.contract.ResearchTaskType;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import com.sun.net.httpserver.HttpServer;

import static org.junit.jupiter.api.Assertions.*;

class ResearchServiceAgentClientTest {

    @Test
    void runPostsToAgentRunsAndDecodesTypedResultWhenEnabled() {
        AtomicBoolean called = new AtomicBoolean(false);
        WebClient.Builder builder = WebClient.builder()
                .exchangeFunction(request -> {
                    called.set(true);
                    assertEquals("/agent/runs", request.url().getPath());
                    String responseBody = """
                            {
                              "run_id": "run_java_001",
                              "task_type": "business_driver_deep_dive",
                              "status": "ok",
                              "events": [],
                              "degraded_reasons": [],
                              "final_report": {
                                "ticker": "TSLA",
                                "sections": {
                                  "summary": "Typed agent response"
                                }
                              }
                            }
                            """;
                    return Mono.just(ClientResponse.create(HttpStatus.OK)
                            .header("Content-Type", "application/json")
                            .body(responseBody)
                            .build());
                });
        ResearchServiceAgentClient client = new ResearchServiceAgentClient(
                builder,
                "http://127.0.0.1:8090",
                Duration.ofSeconds(1));

        ResearchAgentResult result = client.run(request()).block();

        assertTrue(called.get());
        assertNotNull(result);
        assertEquals("run_java_001", result.runId());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, result.taskType());
        assertEquals("ok", result.status());
        assertEquals("TSLA", result.finalReport().get("ticker"));
    }

    @Test
    void runDecodesLiveRagResponsesLargerThanDefaultWebClientBuffer() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/agent/runs", exchange -> {
            assertEquals("POST", exchange.getRequestMethod());
            byte[] body = largeAgentResponse().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
        });
        server.start();
        try {
            ResearchServiceAgentClient client = new ResearchServiceAgentClient(
                    WebClient.builder(),
                    "http://127.0.0.1:" + server.getAddress().getPort(),
                    Duration.ofSeconds(5));

            ResearchAgentResult result = client.run(request()).block();

            assertNotNull(result);
            assertEquals("run_large_rag", result.runId());
            assertEquals("Large live RAG response", result.finalReport().get("summary"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void runMapsResearchServiceHttpFailureToUnavailableException() {
        WebClient.Builder builder = WebClient.builder()
                .exchangeFunction(request -> Mono.just(ClientResponse.create(HttpStatus.SERVICE_UNAVAILABLE)
                        .header("Content-Type", "application/json")
                        .body("""
                                {
                                  "detail": "service warming up"
                                }
                                """)
                        .build()));
        ResearchServiceAgentClient client = new ResearchServiceAgentClient(
                builder,
                "http://127.0.0.1:8090",
                Duration.ofSeconds(1));

        ResearchServiceUnavailableException error = assertThrows(
                ResearchServiceUnavailableException.class,
                () -> client.run(request()).block());

        assertTrue(error.getMessage().contains("Python Research Service is unavailable"));
    }

    @Test
    void runMapsConnectionFailureToUnavailableException() {
        ResearchServiceAgentClient client = new ResearchServiceAgentClient(
                WebClient.builder(),
                "http://127.0.0.1:1",
                Duration.ofMillis(500));

        ResearchServiceUnavailableException error = assertThrows(
                ResearchServiceUnavailableException.class,
                () -> client.run(request()).block());

        assertTrue(error.getMessage().contains("Python Research Service is unavailable"));
    }

    private ResearchAgentRequest request() {
        return new ResearchAgentRequest(
                "run_java_001",
                "TSLA",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                "en",
                2);
    }

    private String largeAgentResponse() {
        return """
                {
                  "run_id": "run_large_rag",
                  "task_type": "business_driver_deep_dive",
                  "status": "ok",
                  "events": [],
                  "degraded_reasons": [],
                  "final_report": {
                    "ticker": "AAPL",
                    "summary": "Large live RAG response",
                    "retrieval_records": [
                      {
                        "tool_name": "search_filing_sections",
                        "retrieved_nodes": [
                          {
                            "node_id": "node_1",
                            "text": "%s",
                            "metadata": {
                              "section": "MD&A"
                            }
                          }
                        ]
                      }
                    ]
                  }
                }
                """.formatted("x".repeat(300_000));
    }
}
