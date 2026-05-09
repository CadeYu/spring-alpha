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
 * SEC filing fetch and cleanup service.
 */
@Service
public class SecService {

    private static final String USER_AGENT = "SpringAlpha/1.0 (test@springalpha.com)";
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

    public Mono<String> getLatest10KContent(String ticker) {
        return getLatestFilingContent(ticker);
    }

    public Mono<String> getLatestFilingContent(String ticker) {
        return Mono.fromCallable(() -> {
            if (!financialDataService.isSupported(ticker)) {
                throw new RuntimeException("SEC filing search is unavailable because ticker is not mapped in SEC company_tickers.json: " + ticker);
            }
            log.info("sec_filing_fetch_start ticker={}", ticker);
            String indexUrl = findLatestFilingIndexUrl(ticker, QUARTERLY_FILING_TYPES);

            String docUrl = findPrimaryDocumentUrl(indexUrl, QUARTERLY_FILING_TYPES);

            String content = fetchAndCleanHtml(docUrl);
            log.info("sec_filing_fetch_complete ticker={} chars={}", ticker, content.length());

            return content;
        });
    }

    private String findLatestFilingIndexUrl(String ticker, String[] docTypes) {
        String lookupKey = resolveSearchIdentifier(ticker);
        for (String type : docTypes) {
            for (int attempt = 1; attempt <= 2; attempt++) {
                try {
                    String searchUrl = buildBrowseEdgarSearchUrl(lookupKey, type);

                    log.debug("sec_index_search ticker={} filingType={} attempt={}", ticker, type, attempt);

                    Document doc = Jsoup.connect(searchUrl)
                            .userAgent(USER_AGENT)
                            .timeout(20000)
                            .get();

                    String parsedUrl = extractLatestIndexUrl(doc, type);
                    if (parsedUrl != null) {
                        log.debug("sec_index_search_complete ticker={} filingType={}", ticker, type);
                        return parsedUrl;
                    }
                    break;
                } catch (IOException e) {
                    log.warn("sec_index_search_failed ticker={} filingType={} attempt={} errorCode={}",
                            ticker, type, attempt, e.getClass().getSimpleName());
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
                .timeout(20000)
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
        docUrl = normalizeDocumentUrl(docUrl);

        log.debug("sec_document_download_start");

        Document doc = Jsoup.connect(docUrl)
                .userAgent(USER_AGENT)
                .timeout(30000)
                .maxBodySize(0)
                .get();

        doc.select("script, style, img, svg, iframe, noscript").remove();

        convertTablesToMarkdown(doc);

        String text = doc.body().text();

        text = text.replaceAll("\\s+", " ");
        text = text.replace("{{NEWLINE}}", "\n");
        text = text.replace("{{TABLE_START}}", "\n\n");
        text = text.replace("{{TABLE_END}}", "\n\n");

        text = text.trim();

        int startIndex = locateCoreSectionStart(text);

        if (startIndex != -1) {
            log.debug("sec_core_section_located startIndex={}", startIndex);
            text = text.substring(startIndex);
        } else {
            log.debug("sec_core_section_missing");
        }

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
     * Convert SEC HTML tables to markdown-like text before Jsoup flattens them.
     */
    void convertTablesToMarkdown(Document doc) {
        Elements tables = doc.select("table");
        int count = 0;

        for (Element table : tables) {
            if (table.parent() != null && "table".equalsIgnoreCase(table.parent().tagName())) {
                continue;
            }

            StringBuilder md = new StringBuilder();
            md.append("{{TABLE_START}}");

            Elements rows = table.select("tr");
            if (rows.isEmpty())
                continue;

            int maxCols = 0;
            for (Element row : rows) {
                maxCols = Math.max(maxCols, row.select("th, td").size());
            }
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
                        cellText = cells.get(i).text().trim().replaceAll("\\|", "/");
                    }
                    md.append(" ").append(cellText).append(" |");
                }
                md.append("{{NEWLINE}}");

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

            table.replaceWith(new TextNode(md.toString()));
            count++;
        }
        log.debug("sec_tables_converted count={}", count);
    }

    String[] filingTypesForLatestQuarter() {
        return QUARTERLY_FILING_TYPES.clone();
    }
}
