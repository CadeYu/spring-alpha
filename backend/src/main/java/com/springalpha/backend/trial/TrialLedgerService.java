package com.springalpha.backend.trial;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Service
public class TrialLedgerService {

    private static final int ANONYMOUS_TRIAL_LIMIT = 3;

    private final AnonymousVisitorStore anonymousVisitorStore;
    private final Clock clock;

    @Autowired
    public TrialLedgerService(AnonymousVisitorStore anonymousVisitorStore) {
        this(anonymousVisitorStore, Clock.systemUTC());
    }

    TrialLedgerService(AnonymousVisitorStore anonymousVisitorStore, Clock clock) {
        this.anonymousVisitorStore = anonymousVisitorStore;
        this.clock = clock;
    }

    public TrialDecision reserveAnonymousTrial(UUID visitorId, Optional<String> ipHash) {
        UUID trialRunId = UUID.randomUUID();
        TrialDecision decision = authorizeAnonymousTrial(visitorId, trialRunId, ipHash);
        if (decision.isAllowed()) {
            confirmAnonymousTrial(visitorId, trialRunId, ipHash);
        }
        return decision;
    }

    public TrialDecision authorizeAnonymousTrial(UUID visitorId, UUID trialRunId, Optional<String> ipHash) {
        Instant now = Instant.now(clock);
        AnonymousVisitor visitor = anonymousVisitorStore.findById(visitorId)
                .orElseGet(() -> AnonymousVisitor.builder()
                        .visitorId(visitorId)
                        .firstSeenAt(now)
                        .build());

        visitor.setLastSeenAt(now);
        ipHash.ifPresent(visitor::setIpHash);

        if (isCurrentConfirmedRun(visitor, trialRunId)) {
            anonymousVisitorStore.save(visitor);
            return TrialDecision.allow();
        }

        if (visitor.getTrialUsedCount() >= ANONYMOUS_TRIAL_LIMIT) {
            anonymousVisitorStore.save(visitor);
            return trialExhausted();
        }

        if (ipHash.filter(hash -> anonymousVisitorStore.sumTrialUsedCountByIpHash(hash) >= ANONYMOUS_TRIAL_LIMIT)
                .isPresent()) {
            anonymousVisitorStore.save(visitor);
            return trialExhausted();
        }

        anonymousVisitorStore.save(visitor);
        return TrialDecision.allow();
    }

    public void confirmAnonymousTrial(UUID visitorId, UUID trialRunId, Optional<String> ipHash) {
        Instant now = Instant.now(clock);
        AnonymousVisitor visitor = anonymousVisitorStore.findById(visitorId)
                .orElseGet(() -> AnonymousVisitor.builder()
                        .visitorId(visitorId)
                        .firstSeenAt(now)
                        .build());

        visitor.setLastSeenAt(now);
        ipHash.ifPresent(visitor::setIpHash);
        if (!isCurrentConfirmedRun(visitor, trialRunId)) {
            visitor.setTrialUsedCount(Math.min(ANONYMOUS_TRIAL_LIMIT, visitor.getTrialUsedCount() + 1));
        }
        if (visitor.getTrialUsedAt() == null) {
            visitor.setTrialUsedAt(now);
        }
        visitor.setTrialRunId(trialRunId);
        anonymousVisitorStore.save(visitor);
    }

    private boolean isCurrentConfirmedRun(AnonymousVisitor visitor, UUID trialRunId) {
        return visitor.getTrialUsedCount() > 0 && trialRunId.equals(visitor.getTrialRunId());
    }

    private TrialDecision trialExhausted() {
        return TrialDecision.deny(
                "TRIAL_EXHAUSTED",
                "Anonymous trial has already been used. Sign in and bring your own provider key to continue.");
    }
}
