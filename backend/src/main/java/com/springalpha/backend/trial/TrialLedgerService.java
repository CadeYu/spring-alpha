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
        Instant now = Instant.now(clock);
        AnonymousVisitor visitor = anonymousVisitorStore.findById(visitorId)
                .orElseGet(() -> AnonymousVisitor.builder()
                        .visitorId(visitorId)
                        .firstSeenAt(now)
                        .build());

        visitor.setLastSeenAt(now);
        ipHash.ifPresent(visitor::setIpHash);

        if (visitor.getTrialUsedAt() != null) {
            anonymousVisitorStore.save(visitor);
            return TrialDecision.deny(
                    "TRIAL_EXHAUSTED",
                    "Anonymous trial has already been used. Sign in and bring your own provider key to continue.");
        }

        visitor.setTrialUsedAt(now);
        visitor.setTrialRunId(UUID.randomUUID());
        anonymousVisitorStore.save(visitor);
        return TrialDecision.allow();
    }
}
