package com.springalpha.backend.service.research;

public class ResearchServiceUnavailableException extends RuntimeException {

    public ResearchServiceUnavailableException(String message) {
        super(message);
    }

    public ResearchServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
