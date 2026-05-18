package com.springalpha.backend.trial;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

class InMemoryAnonymousVisitorRepository implements AnonymousVisitorStore {

    private final Map<UUID, AnonymousVisitor> visitors = new HashMap<>();

    @Override
    public Optional<AnonymousVisitor> findById(UUID visitorId) {
        return Optional.ofNullable(visitors.get(visitorId));
    }

    @Override
    public AnonymousVisitor save(AnonymousVisitor visitor) {
        visitors.put(visitor.getVisitorId(), visitor);
        return visitor;
    }
}
