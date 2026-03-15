package com.springalpha.backend.financial.cache;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Entity
@Table(name = "market_data_cache")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MarketDataCacheEntry {

    @Id
    @Column(name = "cache_key", nullable = false, length = 191)
    private String cacheKey;

    @Column(name = "payload_json", nullable = false, columnDefinition = "TEXT")
    private String payloadJson;

    @Column(name = "source", nullable = false, length = 32)
    private String source;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
}
