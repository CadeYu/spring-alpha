package com.springalpha.backend.service;

import com.springalpha.backend.financial.service.FinancialDataService;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class SecServiceTest {

    private final SecService secService = new SecService(new NoopFinancialDataService());

    @Test
    void extractPrimaryDocumentUrlPrefersRelativeTenQLink() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <table class="tableFile">
                      <tr>
                        <th>Seq</th><th>Description</th><th>Document</th><th>Type</th>
                      </tr>
                      <tr>
                        <td>1</td>
                        <td>Quarterly report</td>
                        <td><a href="/Archives/edgar/data/1318605/0001/tsla-20260331.htm">tsla-20260331.htm</a></td>
                        <td>10-Q</td>
                      </tr>
                    </table>
                  </body>
                </html>
                """);

        String url = secService.extractPrimaryDocumentUrl(
                doc,
                "https://www.sec.gov/Archives/edgar/data/1318605/0001/0001-index.htm");

        assertEquals("https://www.sec.gov/Archives/edgar/data/1318605/0001/tsla-20260331.htm", url);
    }

    @Test
    void extractPrimaryDocumentUrlBuildsAbsoluteUrlFromSiblingQuarterlyPath() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <table class="tableFile">
                      <tr>
                        <th>Seq</th><th>Description</th><th>Document</th><th>Type</th>
                      </tr>
                      <tr>
                        <td>1</td>
                        <td>Quarterly report</td>
                        <td><a href="tsla-20260331.htm">tsla-20260331.htm</a></td>
                        <td>10-Q</td>
                      </tr>
                    </table>
                  </body>
                </html>
                """);

        String url = secService.extractPrimaryDocumentUrl(
                doc,
                "https://www.sec.gov/Archives/edgar/data/1318605/0001/0001-index.htm");

        assertEquals("https://www.sec.gov/Archives/edgar/data/1318605/0001/tsla-20260331.htm", url);
    }

    @Test
    void normalizeDocumentUrlRemovesIxDocViewerPrefix() {
        String normalized = secService.normalizeDocumentUrl(
                "https://www.sec.gov/ix?doc=/Archives/edgar/data/1318605/0001/tsla-20251231.htm");

        assertEquals("https://www.sec.gov/Archives/edgar/data/1318605/0001/tsla-20251231.htm", normalized);
    }

    @Test
    void extractLatestIndexUrlReturnsLatestMatchingTenQLink() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <table class="tableFile2">
                      <tr>
                        <th>Filings</th><th>Format</th><th>Description</th><th>Filing Date</th>
                      </tr>
                      <tr>
                        <td>8-K</td>
                        <td><a href="/Archives/edgar/data/1318605/0000/8k-index.htm">documents</a></td>
                        <td>current report</td>
                        <td>2026-01-01</td>
                      </tr>
                      <tr>
                        <td>10-Q</td>
                        <td><a href="/Archives/edgar/data/1318605/0001/10q-index.htm">documents</a></td>
                        <td>quarterly report</td>
                        <td>2026-04-24</td>
                      </tr>
                    </table>
                  </body>
                </html>
                """);

        String url = secService.extractLatestIndexUrl(doc, "10-Q");

        assertEquals("https://www.sec.gov/Archives/edgar/data/1318605/0001/10q-index.htm", url);
    }

    @Test
    void locateCoreSectionStartFallsBackToItem7WhenKeywordMissing() {
        String text = "Forward-looking statements. Item 7. Results of Operations and liquidity discussion begins here.";

        int startIndex = secService.locateCoreSectionStart(text);

        assertEquals(text.indexOf("Item 7."), startIndex);
    }

    @Test
    void locateCoreSectionStartReturnsMinusOneWhenNoCoreSectionFound() {
        int startIndex = secService.locateCoreSectionStart("Introduction and business overview only.");

        assertEquals(-1, startIndex);
    }

    @Test
    void convertTablesToMarkdownPreservesTabularContent() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <table>
                      <tr><th>Year</th><th>Revenue</th></tr>
                      <tr><td>2025</td><td>$100</td></tr>
                    </table>
                  </body>
                </html>
                """);

        secService.convertTablesToMarkdown(doc);

        String text = doc.body().text();
        assertTrue(text.contains("{{TABLE_START}}"));
        assertTrue(text.contains("| Year | Revenue |"));
        assertTrue(text.contains("| 2025 | $100 |"));
    }

    @Test
    void extractPrimaryDocumentUrlSupportsQuarterlyTenQLink() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <table class="tableFile">
                      <tr>
                        <th>Seq</th><th>Description</th><th>Document</th><th>Type</th>
                      </tr>
                      <tr>
                        <td>1</td>
                        <td>Quarterly report</td>
                        <td><a href="/Archives/edgar/data/320193/0001/aapl-20260328.htm">aapl-20260328.htm</a></td>
                        <td>10-Q</td>
                      </tr>
                    </table>
                  </body>
                </html>
                """);

        String url = secService.extractPrimaryDocumentUrl(
                doc,
                "https://www.sec.gov/Archives/edgar/data/320193/0001/0001-index.htm",
                secService.filingTypesForLatestQuarter());

        assertEquals("https://www.sec.gov/Archives/edgar/data/320193/0001/aapl-20260328.htm", url);
    }

    @Test
    void latestQuarterFilingTypesOnlyIncludeQuarterlyForms() {
        assertArrayEquals(new String[] { "10-Q", "10-Q/A" }, secService.filingTypesForLatestQuarter());
    }

    @Test
    void buildBrowseEdgarSearchUrlUsesResolvedCikWhenAvailable() {
        SecService service = new SecService(new NoopFinancialDataService() {
            @Override
            public Optional<String> resolveSecSearchIdentifier(String ticker) {
                return Optional.of("0001652044");
            }
        });

        String url = service.buildBrowseEdgarSearchUrl(
                service.getFinancialDataService().resolveSecSearchIdentifier("GOOGL").orElse("GOOGL"),
                "10-Q");

        assertTrue(url.contains("CIK=0001652044"));
        assertTrue(url.contains("type=10-Q"));
    }

    @Test
    void getLatestFilingContentFailsFastWhenTickerIsNotSupportedBySecDirectory() {
        SecService service = new SecService(new NoopFinancialDataService() {
            @Override
            public boolean isSupported(String ticker) {
                return false;
            }
        });

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.getLatestFilingContent("XYZ").block());

        assertTrue(ex.getMessage().contains("not mapped in SEC company_tickers.json"));
    }

    private static class NoopFinancialDataService implements FinancialDataService {

        @Override
        public com.springalpha.backend.financial.model.FinancialFacts getFinancialFacts(String ticker) {
            return null;
        }

        @Override
        public boolean isSupported(String ticker) {
            return false;
        }

        @Override
        public java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(
                String ticker) {
            return java.util.List.of();
        }

        @Override
        public String[] getSupportedTickers() {
            return new String[0];
        }
    }
}
