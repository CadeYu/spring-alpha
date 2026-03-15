package com.springalpha.backend.controller;

import com.springalpha.backend.financial.service.FmpQuotaExceededException;
import com.springalpha.backend.financial.service.UnsupportedTickerCategoryException;
import com.springalpha.backend.service.strategy.ProviderAuthenticationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

import java.util.Map;

@ControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(FmpQuotaExceededException.class)
    public ResponseEntity<Map<String, Object>> handleFmpQuotaExceeded(FmpQuotaExceededException exception) {
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .body(Map.of(
                        "error", exception.getMessage(),
                        "code", "FMP_QUOTA_EXCEEDED",
                        "source", "fmp"));
    }

    @ExceptionHandler(ProviderAuthenticationException.class)
    public ResponseEntity<Map<String, Object>> handleProviderAuthentication(ProviderAuthenticationException exception) {
        return ResponseEntity.status(exception.getStatus())
                .body(Map.of(
                        "error", exception.getMessage(),
                        "code", exception.getCode(),
                        "source", exception.getProvider()));
    }

    @ExceptionHandler(UnsupportedTickerCategoryException.class)
    public ResponseEntity<Map<String, Object>> handleUnsupportedTickerCategory(
            UnsupportedTickerCategoryException exception) {
        return ResponseEntity.unprocessableEntity()
                .body(Map.of(
                        "error", exception.getMessage(),
                        "code", "UNSUPPORTED_TICKER_CATEGORY",
                        "category", exception.getCategory(),
                        "ticker", exception.getTicker(),
                        "source", "classification"));
    }
}
