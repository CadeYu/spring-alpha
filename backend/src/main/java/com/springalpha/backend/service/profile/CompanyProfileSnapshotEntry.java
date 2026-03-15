package com.springalpha.backend.service.profile;

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
@Table(name = "company_profile_snapshot")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CompanyProfileSnapshotEntry {

    @Id
    @Column(name = "snapshot_key", nullable = false, length = 191)
    private String snapshotKey;

    @Column(name = "ticker", nullable = false, length = 32)
    private String ticker;

    @Column(name = "report_type", nullable = false, length = 32)
    private String reportType;

    @Column(name = "period_label", nullable = false, length = 64)
    private String periodLabel;

    @Column(name = "filing_date", length = 32)
    private String filingDate;

    @Column(name = "source_hash", nullable = false, length = 64)
    private String sourceHash;

    @Column(name = "extractor_version", nullable = false, length = 32)
    private String extractorVersion;

    @Column(name = "profile_json", nullable = false, columnDefinition = "TEXT")
    private String profileJson;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
}
