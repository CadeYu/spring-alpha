package com.springalpha.backend.service.profile;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyProfileSnapshotRepository extends JpaRepository<CompanyProfileSnapshotEntry, String> {
}
