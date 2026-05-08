package com.springalpha.backend.service.provider;

import reactor.core.publisher.Mono;

import java.util.List;

public interface ProviderCredentialValidator {

    List<String> availableProviders();

    String defaultProvider();

    Mono<Void> validate(String provider, String apiKey);
}
