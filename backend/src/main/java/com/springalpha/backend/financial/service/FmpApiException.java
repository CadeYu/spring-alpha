package com.springalpha.backend.financial.service;

public class FmpApiException extends RuntimeException {

    public FmpApiException(String message) {
        super(message);
    }

    public FmpApiException(String message, Throwable cause) {
        super(message, cause);
    }
}
