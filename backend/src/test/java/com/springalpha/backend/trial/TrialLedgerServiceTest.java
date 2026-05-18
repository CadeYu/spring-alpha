package com.springalpha.backend.trial;

import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrialLedgerServiceTest {

    @Test
    void anonymousVisitorGetsOneTrialOnly() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        UUID visitorId = UUID.randomUUID();

        assertTrue(service.reserveAnonymousTrial(visitorId, Optional.empty()).isAllowed());
        assertFalse(service.reserveAnonymousTrial(visitorId, Optional.empty()).isAllowed());
    }
}
