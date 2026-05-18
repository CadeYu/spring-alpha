package com.springalpha.backend.trial;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface AnonymousVisitorRepository extends JpaRepository<AnonymousVisitor, UUID>, AnonymousVisitorStore {
}
