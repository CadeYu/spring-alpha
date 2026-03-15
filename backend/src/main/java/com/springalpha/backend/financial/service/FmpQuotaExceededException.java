package com.springalpha.backend.financial.service;

public class FmpQuotaExceededException extends FmpApiException {

    public FmpQuotaExceededException(String message) {
        super(message);
    }
}
