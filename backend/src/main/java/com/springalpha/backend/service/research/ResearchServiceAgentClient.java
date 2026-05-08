package com.springalpha.backend.service.research;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ExchangeStrategies;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Service
public class ResearchServiceAgentClient implements ResearchAgentClient {

    private static final int MAX_RESPONSE_BYTES = 4 * 1024 * 1024;

    private final Duration timeout;
    private final WebClient webClient;

    public ResearchServiceAgentClient(
            WebClient.Builder webClientBuilder,
            @Value("${app.research-service.base-url:http://127.0.0.1:8090}") String baseUrl,
            @Value("${app.research-service.timeout:PT75S}") Duration timeout) {
        this.timeout = timeout;
        this.webClient = webClientBuilder
                .baseUrl(baseUrl)
                .exchangeStrategies(ExchangeStrategies.builder()
                        .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(MAX_RESPONSE_BYTES))
                        .build())
                .build();
    }

    @Override
    public Mono<ResearchAgentResult> run(ResearchAgentRequest request) {
        return webClient.post()
                .uri("/agent/runs")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(ResearchAgentResult.class)
                .timeout(timeout)
                .filter(result -> result.finalReport() != null)
                .onErrorMap(this::mapUnavailable);
    }

    private Throwable mapUnavailable(Throwable error) {
        if (error instanceof ResearchServiceUnavailableException) {
            return error;
        }
        if (error instanceof WebClientResponseException responseException) {
            return new ResearchServiceUnavailableException(
                    "Python Research Service is unavailable: HTTP " + responseException.getStatusCode().value(),
                    error);
        }
        if (error instanceof WebClientRequestException || error instanceof TimeoutException) {
            return new ResearchServiceUnavailableException(
                    "Python Research Service is unavailable: " + error.getMessage(),
                    error);
        }
        return error;
    }
}
