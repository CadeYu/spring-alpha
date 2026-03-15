package com.springalpha.backend.financial.cache;

import org.springframework.data.jpa.repository.JpaRepository;

public interface MarketDataCacheRepository extends JpaRepository<MarketDataCacheEntry, String> {
}
