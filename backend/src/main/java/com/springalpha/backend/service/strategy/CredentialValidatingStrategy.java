package com.springalpha.backend.service.strategy;

import reactor.core.publisher.Mono;

public interface CredentialValidatingStrategy {

    Mono<Void> validateCredentials(String apiKeyOverride);
}
