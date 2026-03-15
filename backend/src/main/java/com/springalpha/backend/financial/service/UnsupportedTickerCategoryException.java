package com.springalpha.backend.financial.service;

public class UnsupportedTickerCategoryException extends RuntimeException {

    private final String ticker;
    private final String category;

    public UnsupportedTickerCategoryException(String ticker, String category, String message) {
        super(message);
        this.ticker = ticker;
        this.category = category;
    }

    public String getTicker() {
        return ticker;
    }

    public String getCategory() {
        return category;
    }
}
