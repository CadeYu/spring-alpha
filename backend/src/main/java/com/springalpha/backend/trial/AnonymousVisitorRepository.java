package com.springalpha.backend.trial;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.UUID;

public interface AnonymousVisitorRepository extends JpaRepository<AnonymousVisitor, UUID>, AnonymousVisitorStore {

    @Override
    @Query("select coalesce(sum(visitor.trialUsedCount), 0) from AnonymousVisitor visitor where visitor.ipHash = :ipHash")
    long sumTrialUsedCountByIpHash(@Param("ipHash") String ipHash);
}
