package com.springalpha.backend.controller;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import com.springalpha.backend.trial.TrialAccessException;
import com.springalpha.backend.trial.TrialDecision;
import com.springalpha.backend.trial.TrialLedgerService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/**
 * SEC 财报控制器 (Controller)
 * <p>
 * 提供与 SEC 财报相关的 API 接口。
 * 主要功能:
 * 1. 触发 AI 分析任务 (`/analyze/{ticker}`)
 * 2. 获取原始季度 filing 文本 (`/filing/{ticker}`) - 用于调试 RAG 内容
 */
@RestController
@RequestMapping("/api/sec")
@CrossOrigin(origins = "*")
public class SecController {
    private static final String REPORT_TYPE_QUARTERLY = "quarterly";

    private static final Logger log = LoggerFactory.getLogger(SecController.class);

    private final SecService secService;
    private final FinancialAnalysisService analysisService;
    private final TrialLedgerService trialLedgerService;

    public SecController(
            SecService secService,
            FinancialAnalysisService analysisService,
            TrialLedgerService trialLedgerService) {
        this.secService = secService;
        this.analysisService = analysisService;
        this.trialLedgerService = trialLedgerService;
    }

    /**
     * 触发股票分析 (AI Analysis Endpoint)
     * <p>
     * 使用 Server-Sent Events (SSE) 流式返回分析结果。
     * 这样前端可以像打印机一样实时显示 AI 生成的内容，避免用户长时间等待。
     *
     * @param ticker 股票代码 (e.g., AAPL)
     * @param lang   语言 (en/zh)
     * @param model  BYOK provider (optional)
     */
    @GetMapping(value = "/analyze/{ticker}", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AnalysisReport> analyzeStock(
            @PathVariable String ticker,
            @RequestParam(defaultValue = "en") String lang,
            @RequestParam(defaultValue = "") String model,
            @RequestParam(defaultValue = "") String llmModel,
            @RequestParam(defaultValue = ResearchTaskType.DEFAULT_REQUEST_VALUE) String taskType,
            @RequestHeader HttpHeaders headers) {
        ResearchTaskType researchTaskType = parseResearchTaskType(taskType);
        String providerApiKey = resolveProviderApiKey(headers);
        Optional<AnonymousTrialContext> anonymousTrial = authorizeTrialAccess(headers, providerApiKey);
        log.info("REST request to analyze stock: {}, lang: {}, model: {}, llmModel: {}, taskType: {}",
                ticker, lang, model, llmModel, researchTaskType.requestValue());
        // The analysis flow calls external SEC/Yahoo/Python Agent services, so move
        // the stream off the Netty event loop.
        return Flux.defer(() -> analysisService.analyzeStock(ticker, lang, model, llmModel, providerApiKey,
                researchTaskType))
                .doOnNext(report -> anonymousTrial.ifPresent(this::confirmTrialAccess))
                .subscribeOn(Schedulers.boundedElastic());
    }

    private Optional<AnonymousTrialContext> authorizeTrialAccess(HttpHeaders headers, String providerApiKey) {
        String authMode = Optional.ofNullable(headers.getFirst("X-Auth-Mode"))
                .orElse("anonymous")
                .trim()
                .toLowerCase();
        if (!providerApiKeyIsBlank(providerApiKey)) {
            return Optional.empty();
        }
        if ("authenticated".equals(authMode)) {
            throw new TrialAccessException(
                    "Provider key is required for authenticated analysis.",
                    "PROVIDER_KEY_REQUIRED",
                    HttpStatus.BAD_REQUEST);
        }

        UUID visitorId = parseVisitorId(headers.getFirst("X-Visitor-Id"));
        UUID trialRunId = parseTrialRunId(headers.getFirst("X-Trial-Run-Id"));
        Optional<String> ipHash = Optional.ofNullable(headers.getFirst("X-Client-IP-Hash")).filter(value -> !value.isBlank());
        TrialDecision decision = trialLedgerService.authorizeAnonymousTrial(
                visitorId,
                trialRunId,
                ipHash);
        if (!decision.isAllowed()) {
            throw new TrialAccessException(
                    decision.message(),
                    decision.code(),
                    HttpStatus.PAYMENT_REQUIRED);
        }
        return Optional.of(new AnonymousTrialContext(visitorId, trialRunId, ipHash));
    }

    private void confirmTrialAccess(AnonymousTrialContext context) {
        trialLedgerService.confirmAnonymousTrial(context.visitorId(), context.trialRunId(), context.ipHash());
    }

    private boolean providerApiKeyIsBlank(String providerApiKey) {
        return providerApiKey == null || providerApiKey.isBlank();
    }

    private UUID parseVisitorId(String visitorId) {
        if (visitorId == null || visitorId.isBlank()) {
            throw new TrialAccessException(
                    "Anonymous analysis requires a visitor id.",
                    "AUTH_REQUIRED",
                    HttpStatus.UNAUTHORIZED);
        }
        try {
            return UUID.fromString(visitorId);
        } catch (IllegalArgumentException error) {
            throw new TrialAccessException(
                    "Anonymous analysis requires a valid visitor id.",
                    "AUTH_REQUIRED",
                    HttpStatus.UNAUTHORIZED);
        }
    }

    private UUID parseTrialRunId(String trialRunId) {
        if (trialRunId == null || trialRunId.isBlank()) {
            throw new TrialAccessException(
                    "Anonymous analysis requires a trial run id.",
                    "AUTH_REQUIRED",
                    HttpStatus.UNAUTHORIZED);
        }
        try {
            return UUID.fromString(trialRunId);
        } catch (IllegalArgumentException error) {
            throw new TrialAccessException(
                    "Anonymous analysis requires a valid trial run id.",
                    "AUTH_REQUIRED",
                    HttpStatus.UNAUTHORIZED);
        }
    }

    private String resolveProviderApiKey(HttpHeaders headers) {
        String genericKey = headers.getFirst("X-Provider-API-Key");
        if (genericKey != null && !genericKey.isBlank()) {
            return genericKey;
        }
        String legacyOpenAiKey = headers.getFirst("X-OpenAI-API-Key");
        return legacyOpenAiKey != null && !legacyOpenAiKey.isBlank() ? legacyOpenAiKey : null;
    }

    private ResearchTaskType parseResearchTaskType(String taskType) {
        try {
            return ResearchTaskType.fromRequestValue(taskType);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        }
    }

    private record AnonymousTrialContext(UUID visitorId, UUID trialRunId, Optional<String> ipHash) {
    }

    /**
     * 获取清洗后的季度 filing 文本 (Debug Endpoint)
     * <p>
     * 用于验证 ETL 效果，检查 Markdown 表格是否正确转换。
     */
    @GetMapping({ "/filing/{ticker}", "/10k/{ticker}" })
    public Mono<String> getFilingContent(@PathVariable String ticker) {
        log.info("REST request to get latest quarterly filing content for: {}", ticker);
        return secService.getLatest10KContent(ticker)
                .subscribeOn(Schedulers.boundedElastic())
                .map(content -> {
                    // 只返回前 10000 字符用于预览，防止浏览器卡死
                    if (content.length() > 10000) {
                        return content.substring(0, 10000) + "\n\n... (truncated)";
                    }
                    return content;
                });
    }

    /**
     * 获取可用的 AI 模型列表
     * <p>
     * 返回当前系统支持的 BYOK provider 以及默认 provider。
     */
    @GetMapping("/models")
    public Map<String, Object> getAvailableModels() {
        List<String> models = analysisService.getAvailableModels();
        String defaultModel = analysisService.getDefaultModel();
        return Map.of(
                "models", models,
                "default", defaultModel,
                "count", models.size());
    }

    // Historical Data endpoint for charts
    @GetMapping("/history/{ticker}")
    public Flux<HistoricalDataPoint> getHistory(@PathVariable String ticker) {
        return Mono.fromCallable(() -> secService.getFinancialDataService().getHistoricalData(ticker, REPORT_TYPE_QUARTERLY))
                .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                .flatMapMany(Flux::fromIterable);
    }
}
