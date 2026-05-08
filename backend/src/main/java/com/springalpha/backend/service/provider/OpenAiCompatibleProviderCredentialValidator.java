package com.springalpha.backend.service.provider;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Service
public class OpenAiCompatibleProviderCredentialValidator implements ProviderCredentialValidator {

    private static final Duration VALIDATION_TIMEOUT = Duration.ofSeconds(10);

    private final WebClient.Builder webClientBuilder;
    private final String defaultProvider;
    private final Map<String, ProviderConfig> providers;

    public OpenAiCompatibleProviderCredentialValidator(
            WebClient.Builder webClientBuilder,
            @Value("${app.ai-provider:siliconflow}") String defaultProvider,
            @Value("${app.siliconflow.base-url:https://api.siliconflow.cn/v1}") String siliconFlowBaseUrl,
            @Value("${app.openai.base-url:https://api.openai.com/v1}") String openAiBaseUrl,
            @Value("${app.gemini.base-url:https://generativelanguage.googleapis.com}") String geminiBaseUrl) {
        this.webClientBuilder = webClientBuilder;
        this.defaultProvider = normalizeProvider(defaultProvider);
        this.providers = Map.of(
                "gemini", new ProviderConfig("gemini", "Gemini", geminiBaseUrl),
                "openai", new ProviderConfig("openai", "OpenAI", openAiBaseUrl),
                "siliconflow", new ProviderConfig("siliconflow", "SiliconFlow", siliconFlowBaseUrl));
    }

    @Override
    public List<String> availableProviders() {
        return providers.keySet().stream().sorted().toList();
    }

    @Override
    public String defaultProvider() {
        return providers.containsKey(defaultProvider) ? defaultProvider : "siliconflow";
    }

    @Override
    public Mono<Void> validate(String provider, String apiKey) {
        ProviderConfig config = providerConfig(provider);
        String effectiveApiKey = apiKey == null ? "" : apiKey.trim();
        if (effectiveApiKey.isBlank()) {
            return Mono.error(new ProviderAuthenticationException(
                    config.displayName() + " API key is required for BYOK mode",
                    config.id(),
                    config.id().toUpperCase(Locale.ROOT) + "_API_KEY_MISSING",
                    HttpStatus.BAD_REQUEST));
        }

        return webClientBuilder.clone()
                .baseUrl(config.baseUrl())
                .defaultHeader("Authorization", "Bearer " + effectiveApiKey)
                .build()
                .get()
                .uri("/models")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(VALIDATION_TIMEOUT)
                .then()
                .onErrorResume(error -> Mono.error(mapProviderException(config, error)));
    }

    private ProviderConfig providerConfig(String provider) {
        String providerId = normalizeProvider(provider);
        ProviderConfig config = providers.get(providerId);
        if (config == null) {
            throw new IllegalArgumentException("Unsupported provider: " + providerId);
        }
        return config;
    }

    private String normalizeProvider(String provider) {
        return provider == null || provider.isBlank()
                ? "siliconflow"
                : provider.trim().toLowerCase(Locale.ROOT);
    }

    private ProviderAuthenticationException mapProviderException(ProviderConfig config, Throwable error) {
        if (error instanceof ProviderAuthenticationException providerAuthenticationException) {
            return providerAuthenticationException;
        }
        if (error instanceof WebClientResponseException responseException
                && (responseException.getStatusCode().value() == 401
                        || responseException.getStatusCode().value() == 403)) {
            return new ProviderAuthenticationException(
                    config.displayName() + " API key is invalid or unauthorized for this project",
                    config.id(),
                    config.id().toUpperCase(Locale.ROOT) + "_API_KEY_INVALID",
                    HttpStatus.UNAUTHORIZED);
        }
        return new ProviderAuthenticationException(
                config.displayName() + " API key validation failed: " + error.getMessage(),
                config.id(),
                config.id().toUpperCase(Locale.ROOT) + "_API_KEY_VALIDATION_FAILED",
                HttpStatus.BAD_GATEWAY);
    }

    private record ProviderConfig(String id, String displayName, String baseUrl) {
    }
}
