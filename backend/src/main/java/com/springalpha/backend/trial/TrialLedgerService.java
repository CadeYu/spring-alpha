package com.springalpha.backend.trial;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

@Service
public class TrialLedgerService {

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

        if (isUsedByAnotherRun(visitor, trialRunId)) {
            anonymousVisitorStore.save(visitor);
            return trialExhausted();
        }

        if (visitor.getTrialUsedAt() == null
                && ipHash.filter(anonymousVisitorStore::existsByIpHashAndTrialUsedAtIsNotNull).isPresent()) {
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
        visitor.setTrialUsedAt(now);
        visitor.setTrialRunId(trialRunId);
        anonymousVisitorStore.save(visitor);
    }

    private boolean isUsedByAnotherRun(AnonymousVisitor visitor, UUID trialRunId) {
        return visitor.getTrialUsedAt() != null && !trialRunId.equals(visitor.getTrialRunId());
    }

    private TrialDecision trialExhausted() {
        return TrialDecision.deny(
                "TRIAL_EXHAUSTED",
                "Anonymous trial has already been used. Sign in and bring your own provider key to continue.");
    }
}
