package com.springalpha.backend.service.provider;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
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

    private static final Duration DEFAULT_VALIDATION_TIMEOUT = Duration.ofSeconds(30);
    private static final Logger log = LoggerFactory.getLogger(OpenAiCompatibleProviderCredentialValidator.class);

    private final WebClient.Builder webClientBuilder;
    private final Duration validationTimeout;
    private final String defaultProvider;
    private final Map<String, ProviderConfig> providers;
    private final Map<String, String> configuredApiKeys;

    @Autowired
    public OpenAiCompatibleProviderCredentialValidator(
            WebClient.Builder webClientBuilder,
            @Value("${app.ai-provider:siliconflow}") String defaultProvider,
            @Value("${app.siliconflow.base-url:https://api.siliconflow.cn/v1}") String siliconFlowBaseUrl,
            @Value("${app.openai.base-url:https://api.openai.com/v1}") String openAiBaseUrl,
            @Value("${app.gemini.base-url:https://generativelanguage.googleapis.com}") String geminiBaseUrl,
            @Value("${app.provider-validation-timeout:PT30S}") Duration validationTimeout,
            @Value("${app.siliconflow.api-key:}") String siliconFlowApiKey,
            @Value("${app.openai.api-key:}") String openAiApiKey,
            @Value("${app.gemini.api-key:}") String geminiApiKey) {
        this(
                webClientBuilder,
                defaultProvider,
                siliconFlowBaseUrl,
                openAiBaseUrl,
                geminiBaseUrl,
                validationTimeout,
                Map.of(
                        "siliconflow", normalizeKey(siliconFlowApiKey),
                        "openai", normalizeKey(openAiApiKey),
                        "gemini", normalizeKey(geminiApiKey)));
    }

    OpenAiCompatibleProviderCredentialValidator(
            WebClient.Builder webClientBuilder,
            String defaultProvider,
            String siliconFlowBaseUrl,
            String openAiBaseUrl,
            String geminiBaseUrl,
            Duration validationTimeout) {
        this(
                webClientBuilder,
                defaultProvider,
                siliconFlowBaseUrl,
                openAiBaseUrl,
                geminiBaseUrl,
                validationTimeout,
                Map.of());
    }

    OpenAiCompatibleProviderCredentialValidator(
            WebClient.Builder webClientBuilder,
            String defaultProvider,
            String siliconFlowBaseUrl,
            String openAiBaseUrl,
            String geminiBaseUrl,
            Duration validationTimeout,
            Map<String, String> configuredApiKeys) {
        this.webClientBuilder = webClientBuilder;
        this.validationTimeout = validationTimeout;
        this.defaultProvider = normalizeProvider(defaultProvider);
        this.providers = Map.of(
                "gemini", new ProviderConfig("gemini", "Gemini", geminiBaseUrl),
                "openai", new ProviderConfig("openai", "OpenAI", openAiBaseUrl),
                "siliconflow", new ProviderConfig("siliconflow", "SiliconFlow", siliconFlowBaseUrl));
        this.configuredApiKeys = configuredApiKeys == null ? Map.of() : Map.copyOf(configuredApiKeys);
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
        String effectiveApiKey = normalizeKey(apiKey);
        if (effectiveApiKey.isBlank()) {
            effectiveApiKey = configuredApiKeys.getOrDefault(config.id(), "");
        }
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
                .timeout(validationTimeout)
                .then()
                .onErrorResume(error -> mapProviderException(config, error));
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

    private static String normalizeKey(String apiKey) {
        return apiKey == null ? "" : apiKey.trim();
    }

    private Mono<Void> mapProviderException(ProviderConfig config, Throwable error) {
        if (error instanceof ProviderAuthenticationException providerAuthenticationException) {
            return Mono.error(providerAuthenticationException);
        }
        if (error instanceof WebClientResponseException responseException
                && (responseException.getStatusCode().value() == 401
                        || responseException.getStatusCode().value() == 403)) {
            return Mono.error(new ProviderAuthenticationException(
                            config.displayName() + " API key is invalid or unauthorized for this project",
                            config.id(),
                            config.id().toUpperCase(Locale.ROOT) + "_API_KEY_INVALID",
                            HttpStatus.UNAUTHORIZED));
        }
        log.warn("provider_key_validation_soft_failed provider={} error={}", config.id(),
                error.getClass().getSimpleName());
        return Mono.empty();
    }

    private record ProviderConfig(String id, String displayName, String baseUrl) {
    }
}
