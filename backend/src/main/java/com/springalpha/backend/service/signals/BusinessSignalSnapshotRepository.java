package com.springalpha.backend.service.signals;

import org.springframework.data.jpa.repository.JpaRepository;

public interface BusinessSignalSnapshotRepository extends JpaRepository<BusinessSignalSnapshotEntry, String> {
}
