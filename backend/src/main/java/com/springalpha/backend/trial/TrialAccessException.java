package com.springalpha.backend.trial;

import org.springframework.http.HttpStatus;

public class TrialAccessException extends RuntimeException {

    private final String code;
    private final HttpStatus status;

    public TrialAccessException(String message, String code, HttpStatus status) {
        super(message);
        this.code = code;
        this.status = status;
    }

    public String getCode() {
        return code;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
