package com.springalpha.backend.service.provider;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.*;

class OpenAiCompatibleProviderCredentialValidatorTest {

    @Test
    void availableProvidersAreStableForByokUi() {
        OpenAiCompatibleProviderCredentialValidator validator = validatorReturning(HttpStatus.OK);

        assertEquals(java.util.List.of("gemini", "openai", "siliconflow"), validator.availableProviders());
        assertEquals("siliconflow", validator.defaultProvider());
    }

    @Test
    void validateRejectsMissingApiKeyBeforeHttpCall() {
        OpenAiCompatibleProviderCredentialValidator validator = validatorReturning(HttpStatus.OK);

        ProviderAuthenticationException error = assertThrows(ProviderAuthenticationException.class,
                () -> validator.validate("siliconflow", " ").block());

        assertEquals("SILICONFLOW_API_KEY_MISSING", error.getCode());
        assertEquals(HttpStatus.BAD_REQUEST, error.getStatus());
    }

    @Test
    void validateMapsUnauthorizedProviderResponse() {
        OpenAiCompatibleProviderCredentialValidator validator = validatorReturning(HttpStatus.UNAUTHORIZED);

        ProviderAuthenticationException error = assertThrows(ProviderAuthenticationException.class,
                () -> validator.validate("siliconflow", "secret").block());

        assertEquals("SILICONFLOW_API_KEY_INVALID", error.getCode());
        assertEquals(HttpStatus.UNAUTHORIZED, error.getStatus());
    }

    @Test
    void validateCallsProviderModelsEndpointWithBearerToken() {
        java.util.concurrent.atomic.AtomicReference<String> authorization = new java.util.concurrent.atomic.AtomicReference<>();
        WebClient.Builder builder = WebClient.builder()
                .exchangeFunction(request -> {
                    authorization.set(request.headers().getFirst("Authorization"));
                    assertTrue(request.url().getPath().endsWith("/models"));
                    return Mono.just(ClientResponse.create(HttpStatus.OK)
                            .header("Content-Type", "application/json")
                            .body("{}")
                            .build());
                });
        OpenAiCompatibleProviderCredentialValidator validator = new OpenAiCompatibleProviderCredentialValidator(
                builder,
                "siliconflow",
                "https://siliconflow.example/v1",
                "https://openai.example/v1",
                "https://gemini.example/v1beta/openai",
                Duration.ofSeconds(30));

        validator.validate("siliconflow", "secret").block();

        assertEquals("Bearer secret", authorization.get());
    }

    @Test
    void validateDoesNotBlockLiveAgentWhenProviderPreflightTimesOut() {
        WebClient.Builder builder = WebClient.builder()
                .exchangeFunction(request -> Mono.never());
        OpenAiCompatibleProviderCredentialValidator validator = new OpenAiCompatibleProviderCredentialValidator(
                builder,
                "siliconflow",
                "https://siliconflow.example/v1",
                "https://openai.example/v1",
                "https://gemini.example/v1beta/openai",
                Duration.ofMillis(20));

        assertDoesNotThrow(() -> validator.validate("siliconflow", "secret").block());
    }

    private OpenAiCompatibleProviderCredentialValidator validatorReturning(HttpStatus status) {
        WebClient.Builder builder = WebClient.builder()
                .exchangeFunction(request -> Mono.just(ClientResponse.create(status)
                        .header("Content-Type", "application/json")
                        .body("{}")
                        .build()));
        return new OpenAiCompatibleProviderCredentialValidator(
                builder,
                "siliconflow",
                "https://siliconflow.example/v1",
                "https://openai.example/v1",
                "https://gemini.example/v1beta/openai",
                Duration.ofSeconds(30));
    }
}
