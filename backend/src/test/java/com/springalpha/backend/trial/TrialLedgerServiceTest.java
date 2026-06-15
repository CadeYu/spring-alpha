package com.springalpha.backend.trial;

import org.junit.jupiter.api.Test;

import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TrialLedgerServiceTest {

    @Test
    void anonymousVisitorGetsThreeTrialRunsOnly() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        UUID visitorId = UUID.randomUUID();

        for (int attempt = 0; attempt < 3; attempt++) {
            UUID runId = UUID.randomUUID();
            assertTrue(service.authorizeAnonymousTrial(visitorId, runId, Optional.empty()).isAllowed());
            service.confirmAnonymousTrial(visitorId, runId, Optional.empty());
        }

        assertFalse(service.authorizeAnonymousTrial(visitorId, UUID.randomUUID(), Optional.empty()).isAllowed());
    }

    @Test
    void anonymousTickerRunCanAuthorizeMultipleAgentTasksWithoutConsumingExtraTrials() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        UUID visitorId = UUID.randomUUID();
        UUID runId = UUID.randomUUID();

        assertTrue(service.authorizeAnonymousTrial(visitorId, runId, Optional.empty()).isAllowed());
        assertTrue(service.authorizeAnonymousTrial(visitorId, runId, Optional.empty()).isAllowed());
        assertTrue(service.authorizeAnonymousTrial(visitorId, runId, Optional.empty()).isAllowed());

        service.confirmAnonymousTrial(visitorId, runId, Optional.empty());
        service.confirmAnonymousTrial(visitorId, runId, Optional.empty());
        service.confirmAnonymousTrial(visitorId, runId, Optional.empty());

        assertTrue(service.authorizeAnonymousTrial(visitorId, runId, Optional.empty()).isAllowed());

        for (int attempt = 0; attempt < 2; attempt++) {
            UUID nextRunId = UUID.randomUUID();
            assertTrue(service.authorizeAnonymousTrial(visitorId, nextRunId, Optional.empty()).isAllowed());
            service.confirmAnonymousTrial(visitorId, nextRunId, Optional.empty());
        }

        assertFalse(service.authorizeAnonymousTrial(visitorId, UUID.randomUUID(), Optional.empty()).isAllowed());
    }

    @Test
    void failedRequestDoesNotConsumeTrialBeforeConfirmation() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        UUID visitorId = UUID.randomUUID();

        assertTrue(service.authorizeAnonymousTrial(visitorId, UUID.randomUUID(), Optional.empty()).isAllowed());
        assertTrue(service.authorizeAnonymousTrial(visitorId, UUID.randomUUID(), Optional.empty()).isAllowed());
    }

    @Test
    void ipHashCannotBypassUsedTrialsWithNewVisitorCookie() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        UUID firstVisitorId = UUID.randomUUID();
        String ipHash = "client-ip-hash";

        for (int attempt = 0; attempt < 3; attempt++) {
            UUID runId = UUID.randomUUID();
            assertTrue(service.authorizeAnonymousTrial(firstVisitorId, runId, Optional.of(ipHash)).isAllowed());
            service.confirmAnonymousTrial(firstVisitorId, runId, Optional.of(ipHash));
        }

        TrialDecision decision = service.authorizeAnonymousTrial(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Optional.of(ipHash));

        assertFalse(decision.isAllowed());
        assertEquals("TRIAL_EXHAUSTED", decision.code());
    }

    @Test
    void ipHashSearchChecksAggregateTrialUsageInsteadOfFirstMatchOnly() {
        InMemoryAnonymousVisitorRepository repository = new InMemoryAnonymousVisitorRepository();
        TrialLedgerService service = new TrialLedgerService(repository);
        String ipHash = "shared-client-ip-hash";

        assertTrue(service.authorizeAnonymousTrial(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Optional.of(ipHash)).isAllowed());

        for (int attempt = 0; attempt < 3; attempt++) {
            UUID usedVisitorId = UUID.randomUUID();
            UUID usedRunId = UUID.randomUUID();
            assertTrue(service.authorizeAnonymousTrial(usedVisitorId, usedRunId, Optional.of(ipHash)).isAllowed());
            service.confirmAnonymousTrial(usedVisitorId, usedRunId, Optional.of(ipHash));
        }

        TrialDecision decision = service.authorizeAnonymousTrial(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Optional.of(ipHash));

        assertFalse(decision.isAllowed());
        assertEquals("TRIAL_EXHAUSTED", decision.code());
    }
}
