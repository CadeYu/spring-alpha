package com.springalpha.backend.trial;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

class InMemoryAnonymousVisitorRepository implements AnonymousVisitorStore {

    private final Map<UUID, AnonymousVisitor> visitors = new LinkedHashMap<>();

    @Override
    public Optional<AnonymousVisitor> findById(UUID visitorId) {
        return Optional.ofNullable(visitors.get(visitorId));
    }

    @Override
    public long sumTrialUsedCountByIpHash(String ipHash) {
        return visitors.values().stream()
                .filter(visitor -> ipHash.equals(visitor.getIpHash()))
                .mapToLong(AnonymousVisitor::getTrialUsedCount)
                .sum();
    }

    @Override
    public AnonymousVisitor save(AnonymousVisitor visitor) {
        visitors.put(visitor.getVisitorId(), visitor);
        return visitor;
    }
}
