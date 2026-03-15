package com.springalpha.backend.service.strategy;

import org.springframework.http.HttpStatus;

public class ProviderAuthenticationException extends RuntimeException {

    private final String provider;
    private final String code;
    private final HttpStatus status;

    public ProviderAuthenticationException(String message, String provider, String code, HttpStatus status) {
        super(message);
        this.provider = provider;
        this.code = code;
        this.status = status;
    }

    public String getProvider() {
        return provider;
    }

    public String getCode() {
        return code;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
