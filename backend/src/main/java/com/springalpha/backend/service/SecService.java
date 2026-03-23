package com.springalpha.backend.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.nodes.TextNode;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.io.IOException;
import java.util.Optional;

/**
 * SEC 服务 (ETL Service)
 * <p>
 * 负责从 SEC EDGAR 官网抓取、清洗和结构化最新季度 filing。
 * 核心功能：
 * 1. **Crawl**: 查找最新财报 URL。
 * 2. **Clean**: 去除 HTML 杂质。
 * 3. **Transform**: 将 HTML 表格转换为 Markdown，保留数据结构 (Table Structure
 * Preservation)。
 */
@Service
public class SecService {

    private static final String USER_AGENT = "SpringAlpha/1.0 (test@springalpha.com)"; // SEC 要求必须带 User-Agent
    private static final String SEC_BASE_URL = "https://www.sec.gov";
    private static final String[] QUARTERLY_FILING_TYPES = new String[] { "10-Q", "10-Q/A" };
    private final com.springalpha.backend.financial.service.FinancialDataService financialDataService;

    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(SecService.class);

    public SecService(com.springalpha.backend.financial.service.FinancialDataService financialDataService) {
        this.financialDataService = financialDataService;
    }

    public com.springalpha.backend.financial.service.FinancialDataService getFinancialDataService() {
        return financialDataService;
    }

    /**
     * 兼容旧名称：获取某股票最新季度 filing 的纯文本内容
     */
    public Mono<String> getLatest10KContent(String ticker) {
        return getLatestFilingContent(ticker);
    }

    public Mono<String> getLatestFilingContent(String ticker) {
        return Mono.fromCallable(() -> {
            if (!financialDataService.isSupported(ticker)) {
                throw new RuntimeException("SEC filing search is unavailable because ticker is not mapped in SEC company_tickers.json: " + ticker);
            }
            log.info("🔍 [1/3] 开始查找 {} 的最新季度财报索引页...", ticker);
            // 1. 找到索引页 URL
            String indexUrl = findLatestFilingIndexUrl(ticker, QUARTERLY_FILING_TYPES);
            log.info("✅ [1/3] 找到索引页: {}", indexUrl);

            log.info("🔍 [2/3] 开始解析主文档链接...");
            // 2. 在索引页中找到主文档 URL
            String docUrl = findPrimaryDocumentUrl(indexUrl, QUARTERLY_FILING_TYPES);
            log.info("✅ [2/3] 找到主文档链接: {}", docUrl);

            log.info("📥 [3/3] 开始下载并清洗 HTML (可能需要较长时间)...");
            // 3. 下载并清洗 HTML
            String content = fetchAndCleanHtml(docUrl);
            log.info("✅ [3/3] 清洗完成！文本长度: {} 字符", content.length());

            return content;
        });
    }

    private String findLatestFilingIndexUrl(String ticker, String[] docTypes) {
        String lookupKey = resolveSearchIdentifier(ticker);
        for (String type : docTypes) {
            // Retry each doc type up to 2 times (SEC can be slow from overseas)
            for (int attempt = 1; attempt <= 2; attempt++) {
                try {
                    String searchUrl = buildBrowseEdgarSearchUrl(lookupKey, type);

                    log.info("🔍 Searching SEC for {} via {} (Type: {}, attempt {}/2)", ticker, lookupKey, type, attempt);

                    Document doc = Jsoup.connect(searchUrl)
                            .userAgent(USER_AGENT)
                            .timeout(20000) // 20s — SEC can be slow from overseas
                            .get();

                    String parsedUrl = extractLatestIndexUrl(doc, type);
                    if (parsedUrl != null) {
                        log.info("✅ Found {} index page: {}", type, parsedUrl);
                        return parsedUrl; // Return immediately if found
                    }
                    break; // Parsed OK but no matching row — no need to retry, try next type
                } catch (IOException e) {
                    log.warn("⚠️ Failed to search {} for {} (attempt {}/2): {}", type, ticker, attempt, e.getMessage());
                    if (attempt < 2) {
                        try {
                            Thread.sleep(2000);
                        } catch (InterruptedException ie) {
                            Thread.currentThread().interrupt();
                        }
                    }
                }
            }
        }

        throw new RuntimeException("No supported SEC filing found for ticker: " + ticker);
    }

    String buildBrowseEdgarSearchUrl(String lookupKey, String filingType) {
        return String.format(
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s&type=%s&dateb=&owner=exclude&count=10",
                lookupKey,
                filingType);
    }

    private String resolveSearchIdentifier(String ticker) {
        Optional<String> resolved = financialDataService.resolveSecSearchIdentifier(ticker);
        return resolved.filter(value -> !value.isBlank()).orElse(ticker);
    }

    String extractLatestIndexUrl(Document doc, String targetType) {
        Elements rows = doc.select("table.tableFile2 tr");

        for (Element row : rows) {
            String docType = row.select("td").first() != null ? row.select("td").first().text() : "";
            if (targetType.equals(docType)) {
                Element link = row.select("a[href]").first();
                if (link != null) {
                    return SEC_BASE_URL + link.attr("href");
                }
            }
        }

        return null;
    }

    private String findPrimaryDocumentUrl(String indexUrl, String[] acceptedTypes) throws IOException {
        Document doc = Jsoup.connect(indexUrl)
                .userAgent(USER_AGENT)
                .timeout(20000) // 20s — SEC can be slow from overseas
                .get();

        return extractPrimaryDocumentUrl(doc, indexUrl, acceptedTypes);
    }

    String extractPrimaryDocumentUrl(Document doc, String indexUrl) {
        return extractPrimaryDocumentUrl(doc, indexUrl, QUARTERLY_FILING_TYPES);
    }

    String extractPrimaryDocumentUrl(Document doc, String indexUrl, String[] acceptedTypes) {
        java.util.Set<String> allowed = java.util.Arrays.stream(acceptedTypes)
                .map(String::trim)
                .collect(java.util.stream.Collectors.toSet());

        Elements rows = doc.select("table.tableFile tr");
        for (Element row : rows) {
            Elements cells = row.select("td");
            if (cells.size() > 3) {
                String type = cells.get(3).text();
                if (allowed.contains(type)) {
                    Element link = cells.get(2).select("a").first();
                    if (link != null) {
                        String href = link.attr("href");
                        if (href.startsWith("/")) {
                            return SEC_BASE_URL + href;
                        } else {
                            String baseUrl = indexUrl.substring(0, indexUrl.lastIndexOf("/"));
                            return baseUrl + "/" + href;
                        }
                    }
                }
            }
        }
        throw new RuntimeException("Primary document not found in index page: " + indexUrl);
    }

    String normalizeDocumentUrl(String docUrl) {
        if (docUrl.contains("/ix?doc=")) {
            return docUrl.replace("/ix?doc=", "");
        }
        return docUrl;
    }

    private String fetchAndCleanHtml(String docUrl) throws IOException {
        // 修复 SEC iXBRL Viewer 链接问题
        // 如果链接包含 /ix?doc=，说明是 JS 查看器页面，需要还原为原始 HTML 链接
        docUrl = normalizeDocumentUrl(docUrl);

        log.info("🌍 最终下载 URL: {}", docUrl);

        // 为了防止季度 filing 太大导致内存溢出，我们限制 maxBodySize
        // 0 表示无限，但在生产环境建议限制，比如 10MB
        Document doc = Jsoup.connect(docUrl)
                .userAgent(USER_AGENT)
                .timeout(30000) // 下载大文件多给点时间
                .maxBodySize(0)
                .get();

        // --- ETL 清洗逻辑 ---

        // 1. 移除无关标签
        doc.select("script, style, img, svg, iframe, noscript").remove();

        // 2. 尝试提取 MD&A (Item 7)
        // 这是一个难点，因为 SEC 格式不统一。
        // MVP 策略：直接获取全文本，依靠 LLM 的长窗口去提取。
        // 优化策略：至少把 HTML 的表格结构转换成文本，或者移除表格只看文字。

        // 3. 将 HTML 表格转换为 Markdown 格式，以保留结构
        convertTablesToMarkdown(doc);

        String text = doc.body().text(); // Jsoup 的 text() 会智能去除 HTML 标签并保留空格

        // 4. 清理空格，但恢复 Markdown 的换行结构
        // 先把所有空白字符(包括换行)压缩成单个空格
        text = text.replaceAll("\\s+", " ");
        // 恢复我们注入的特殊换行符
        text = text.replace("{{NEWLINE}}", "\n");
        // 恢复表格前后的换行
        text = text.replace("{{TABLE_START}}", "\n\n");
        text = text.replace("{{TABLE_END}}", "\n\n");

        text = text.trim();

        // 4. 移除硬编码截断，让 RAG 处理全文
        // 我们保留 MD&A 定位逻辑作为 fallback，或者给 RAG 提供更好的起点，但不再强制截断长度
        // 如果文本实在太长（比如 > 10MB），再考虑物理限制防止 OOM

        // 查找 MD&A 主要是为了确保我们没抓错页面，但为了 RAG，我们返回更多上下文
        int startIndex = locateCoreSectionStart(text);

        // 如果找到了 MD&A，我们可以去掉前面的目录废话，但保留后面的所有内容
        if (startIndex != -1) {
            log.info("🎯 成功定位到核心章节 (MD&A) starting at index: {}", startIndex);
            // 只去掉头部，保留后面所有内容 (直到文件结束)
            text = text.substring(startIndex);
        } else {
            log.warn("⚠️ 未找到核心章节关键词，返回全文。");
        }

        // 安全截断：防止极大文件导致内存溢出 (比如限制 50万字符 ≈ 1MB)
        if (text.length() > 500000) {
            text = text.substring(0, 500000) + "... [Truncated at 500k chars]";
        }

        return text;
    }

    int locateCoreSectionStart(String text) {
        String keyword = "Management's Discussion and Analysis";
        int startIndex = text.lastIndexOf(keyword);

        if (startIndex == -1) {
            startIndex = text.lastIndexOf("Item 7.");
        }

        return startIndex;
    }

    /**
     * 将 HTML 表格转换为 Markdown 格式文本，并替换原节点。
     * <p>
     * **为什么要做这个？**
     * 普通的 `Jsoup.text()` 会把表格扁平化成一串乱序文本：
     * 原文: | Volume | +5% | -> 结果: "Volume +5%" (失去了列对齐关系)
     * <p>
     * **转换后**:
     * | Volume | +5% | (保留了 Markdown 管道符)
     * <p>
     * 这样 LLM (Groq) 在 RAG 检索时，就能理解这是表格，从而正确提取 "Volume" 对应的 "+5%"。
     *
     * @param doc Jsoup Document 对象（会被原地修改）
     */
    void convertTablesToMarkdown(Document doc) {
        Elements tables = doc.select("table");
        int count = 0;

        for (Element table : tables) {
            // 忽略嵌套表格 (只处理最外层)，防止重复处理
            if (table.parent() != null && "table".equalsIgnoreCase(table.parent().tagName())) {
                continue;
            }

            StringBuilder md = new StringBuilder();
            md.append("{{TABLE_START}}"); // 标记表格开始，稍后替换为换行

            Elements rows = table.select("tr");
            if (rows.isEmpty())
                continue;

            // 预处理：计算最大列数，确保每一行都能对齐
            int maxCols = 0;
            for (Element row : rows) {
                maxCols = Math.max(maxCols, row.select("th, td").size());
            }
            // 至少要有两列才转换，单列的表格通常是布局用的，不是数据
            if (maxCols < 1)
                continue;

            boolean headerProcessed = false;

            for (Element row : rows) {
                Elements cells = row.select("th, td");
                if (cells.isEmpty())
                    continue;

                md.append("|");
                for (int i = 0; i < maxCols; i++) {
                    String cellText = "";
                    if (i < cells.size()) {
                        // 清理单元格文本：去除多余空格，转义内部的管道符 "|" 防止破坏 Markdown 结构
                        cellText = cells.get(i).text().trim().replaceAll("\\|", "/");
                    }
                    md.append(" ").append(cellText).append(" |");
                }
                md.append("{{NEWLINE}}"); // 临时换行符，防止 Jsoup.text() 把它吃掉

                // 如果这是第一行，或者包含 th，我们假设它是表头，加上 Markdown 分隔线 |---|---|
                // 简单的启发式：第一行总是加分隔线
                if (!headerProcessed) {
                    md.append("|");
                    for (int i = 0; i < maxCols; i++) {
                        md.append("---|");
                    }
                    md.append("{{NEWLINE}}");
                    headerProcessed = true;
                }
            }

            md.append("{{TABLE_END}}");

            // 关键：用生成的 Markdown 文本替换原始的 HTML <table> 节点
            // 使用 TextNode 包装，这样后续 doc.body().text() 就会包含这段 Markdown
            table.replaceWith(new TextNode(md.toString()));
            count++;
        }
        log.info("📊 Converted {} HTML tables to Markdown format", count);
    }

    String[] filingTypesForLatestQuarter() {
        return QUARTERLY_FILING_TYPES.clone();
    }
}
