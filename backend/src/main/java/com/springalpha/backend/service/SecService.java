package com.springalpha.backend.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.io.IOException;

@Service
public class SecService {

    private static final String USER_AGENT = "SpringAlpha/1.0 (test@springalpha.com)"; // SEC 要求必须带 User-Agent
    private static final String SEC_BASE_URL = "https://www.sec.gov";
    private final com.springalpha.backend.financial.service.FinancialDataService financialDataService;

    private static final org.slf4j.Logger log = org.slf4j.LoggerFactory.getLogger(SecService.class);

    public SecService(com.springalpha.backend.financial.service.FinancialDataService financialDataService) {
        this.financialDataService = financialDataService;
    }

    public com.springalpha.backend.financial.service.FinancialDataService getFinancialDataService() {
        return financialDataService;
    }

    /**
     * 核心业务方法：获取某股票最新的 10-K 纯文本内容
     */
    public Mono<String> getLatest10KContent(String ticker) {
        return Mono.fromCallable(() -> {
            log.info("🔍 [1/3] 开始查找 {} 的最新 10-K 报告索引页...", ticker);
            // 1. 找到索引页 URL
            String indexUrl = findLatest10KIndexUrl(ticker);
            log.info("✅ [1/3] 找到索引页: {}", indexUrl);

            log.info("🔍 [2/3] 开始解析主文档链接...");
            // 2. 在索引页中找到主文档 URL
            String docUrl = findPrimaryDocumentUrl(indexUrl);
            log.info("✅ [2/3] 找到主文档链接: {}", docUrl);

            log.info("📥 [3/3] 开始下载并清洗 HTML (可能需要较长时间)...");
            // 3. 下载并清洗 HTML
            String content = fetchAndCleanHtml(docUrl);
            log.info("✅ [3/3] 清洗完成！文本长度: {} 字符", content.length());

            return content;
        });
    }

    private String findLatest10KIndexUrl(String ticker) {
        // SEC 官方搜索接口 (这里使用 EDGAR Full Text Search 的 API 或者旧版 browse 接口)
        String searchUrl = String.format(
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=%s&type=10-K&dateb=&owner=exclude&count=10",
                ticker);

        try {
            Document doc = Jsoup.connect(searchUrl)
                    .userAgent(USER_AGENT)
                    .timeout(10000)
                    .get();

            Elements rows = doc.select("table.tableFile2 tr");

            for (Element row : rows) {
                String docType = row.select("td").first() != null ? row.select("td").first().text() : "";
                if ("10-K".equals(docType)) {
                    Element link = row.select("a[href]").first();
                    if (link != null) {
                        return SEC_BASE_URL + link.attr("href");
                    }
                }
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to fetch index from SEC: " + e.getMessage(), e);
        }
        throw new RuntimeException("No 10-K found for ticker: " + ticker);
    }

    private String findPrimaryDocumentUrl(String indexUrl) throws IOException {
        Document doc = Jsoup.connect(indexUrl)
                .userAgent(USER_AGENT)
                .timeout(10000)
                .get();

        // 索引页通常有一个表格，列出了该次提交的所有文件。
        // 我们要找 Description 可能是 "10-K" 或者是 Type 为 "10-K" 的第一行文件
        Elements rows = doc.select("table.tableFile tr");
        for (Element row : rows) {
            Elements cells = row.select("td");
            if (cells.size() > 3) {
                // 通常第3列是Document Type
                String type = cells.get(3).text();
                if ("10-K".equals(type)) {
                    Element link = cells.get(2).select("a").first(); // 第3列是文件名链接
                    if (link != null) {
                        // SEC 的链接通常是相对路径 /Archives/...
                        String href = link.attr("href");
                        // 有时候是完整路径，有时候是相对路径，处理一下
                        if (href.startsWith("/")) {
                            return SEC_BASE_URL + href;
                        } else {
                            // 这是一个极其简化的处理，实际 SEC 结构较复杂，通常 index url 去掉最后的文件名就是 base
                            String baseUrl = indexUrl.substring(0, indexUrl.lastIndexOf("/"));
                            return baseUrl + "/" + href;
                        }
                    }
                }
            }
        }
        throw new RuntimeException("Primary 10-K document not found in index page: " + indexUrl);
    }

    private String fetchAndCleanHtml(String docUrl) throws IOException {
        // 修复 SEC iXBRL Viewer 链接问题
        // 如果链接包含 /ix?doc=，说明是 JS 查看器页面，需要还原为原始 HTML 链接
        if (docUrl.contains("/ix?doc=")) {
            docUrl = docUrl.replace("/ix?doc=", "");
        }

        log.info("🌍 最终下载 URL: {}", docUrl);

        // 为了防止 10-K 太大导致内存溢出，我们限制 maxBodySize
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

        String text = doc.body().text(); // Jsoup 的 text() 会智能去除 HTML 标签并保留空格

        // 3. 简单的预处理：去除多余空格
        text = text.replaceAll("\\s+", " ").trim();

        // 4. 移除硬编码截断，让 RAG 处理全文
        // 我们保留 MD&A 定位逻辑作为 fallback，或者给 RAG 提供更好的起点，但不再强制截断长度
        // 如果文本实在太长（比如 > 10MB），再考虑物理限制防止 OOM

        // 查找 MD&A 主要是为了确保我们没抓错页面，但为了 RAG，我们返回更多上下文
        String keyword = "Management's Discussion and Analysis";
        int startIndex = text.lastIndexOf(keyword);

        if (startIndex == -1) {
            startIndex = text.lastIndexOf("Item 7.");
        }

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
}
