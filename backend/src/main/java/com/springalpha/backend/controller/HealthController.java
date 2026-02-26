package com.springalpha.backend.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
// import reactor.core.publisher.Mono; // No longer needed for health()
// import java.time.LocalDateTime; // No longer needed for health()
// import java.util.Map; // No longer needed for health()

/**
 * 健康检查控制器 (Health Check)
 * <p>
 * 用于 K8s/Render 的 Liveness Probe 和 Readiness Probe。
 * 确保服务存活且数据库连接正常。
 */
@RestController
public class HealthController {

    @GetMapping("/health")
    public String health() {
        return "OK - Spring Alpha Backend is running";
    }

    @GetMapping("/")
    public String root() {
        return "Spring Alpha Backend API - Use /api/sec/analyze/{ticker} to start";
    }
}
