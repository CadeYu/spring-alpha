package com.springalpha.backend.trial;

public record TrialDecision(boolean isAllowed, String code, String message) {

    public static TrialDecision allow() {
        return new TrialDecision(true, null, null);
    }

    public static TrialDecision deny(String code, String message) {
        return new TrialDecision(false, code, message);
    }
}
