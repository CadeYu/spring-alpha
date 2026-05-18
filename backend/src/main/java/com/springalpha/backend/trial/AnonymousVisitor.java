package com.springalpha.backend.trial;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "anonymous_visitors")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AnonymousVisitor {

    @Id
    @Column(name = "visitor_id", nullable = false)
    private UUID visitorId;

    @Column(name = "first_seen_at", nullable = false)
    private Instant firstSeenAt;

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    @Column(name = "trial_used_at")
    private Instant trialUsedAt;

    @Column(name = "trial_run_id")
    private UUID trialRunId;

    @Column(name = "ip_hash")
    private String ipHash;

    @Column(name = "blocked_reason")
    private String blockedReason;
}
