package com.springalpha.backend.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.time.LocalDateTime;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class HealthController {

    @GetMapping("/health")
    public Mono<Map<String, Object>> healthCheck() {
        return Mono.just(Map.of(
            "status", "UP",
            "service", "Spring Alpha Backend",
            "timestamp", LocalDateTime.now().toString(),
            "tech", "Java 21 + Spring Boot 3.3 + WebFlux"
        ));
    }
}
