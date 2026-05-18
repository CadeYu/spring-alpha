package com.springalpha.backend.trial;

import java.util.Optional;
import java.util.UUID;

public interface AnonymousVisitorStore {

    Optional<AnonymousVisitor> findById(UUID visitorId);

    boolean existsByIpHashAndTrialUsedAtIsNotNull(String ipHash);

    AnonymousVisitor save(AnonymousVisitor visitor);
}
