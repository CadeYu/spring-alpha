package com.springalpha.backend.service;

import com.springalpha.backend.financial.service.FinancialDataService;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;

import java.io.IOException;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

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
    void cleanFilingDocumentRemovesInlineXbrlMetadataAndStartsAtOperatingDiscussion() {
        Document doc = Jsoup.parse("""
                <html>
                  <body>
                    <ix:header>
                      <ix:hidden>
                        false2026Q20000320193 xbrli:shares iso4217:USD us-gaap:LongTermDebtCurrent
                      </ix:hidden>
                      <ix:references>http://fasb.org/us-gaap/2025</ix:references>
                    </ix:header>
                    <div style="display:none">0000320193 hidden taxonomy payload</div>
                    <h2>Item 2. Management’s Discussion and Analysis of Financial Condition and Results of Operations</h2>
                    <p>Net sales increased because Services demand improved and iPhone demand remained resilient.</p>
                    <h2>Quantitative and Qualitative Disclosures About Market Risk</h2>
                    <p>Derivative instruments may be used to hedge foreign exchange risk.</p>
                  </body>
                </html>
                """);

        String text = secService.cleanFilingDocument(doc);

        assertTrue(text.indexOf("Item 2. Management’s Discussion") < 80);
        assertTrue(text.contains("Services demand improved"));
        assertFalse(text.contains("xbrli:shares"));
        assertFalse(text.contains("hidden taxonomy payload"));
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

    @Test
    void getLatestFilingContentDedupesConcurrentRequestsForTheSameTicker() throws InterruptedException {
        CountDownLatch fetchEntered = new CountDownLatch(1);
        CountDownLatch releaseFetch = new CountDownLatch(1);
        CountDownLatch subscriptionsObserved = new CountDownLatch(2);
        AtomicInteger fetchCount = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        CyclicBarrier startBarrier = new CyclicBarrier(2);

        SecService service = new SecService(new NoopFinancialDataService() {
            @Override
            public boolean isSupported(String ticker) {
                return true;
            }
        }) {
            @Override
            public Mono<String> getLatestFilingContent(String ticker) {
                try {
                    startBarrier.await(5, TimeUnit.SECONDS);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(e);
                } catch (java.util.concurrent.BrokenBarrierException | java.util.concurrent.TimeoutException e) {
                    throw new RuntimeException(e);
                }
                return super.getLatestFilingContent(ticker)
                        .doOnSubscribe(subscription -> subscriptionsObserved.countDown());
            }

            @Override
            String findLatestFilingIndexUrl(String ticker, String[] docTypes) {
                return "https://www.sec.gov/Archives/edgar/data/1318605/0001/0001-index.htm";
            }

            @Override
            String findPrimaryDocumentUrl(String indexUrl, String[] acceptedTypes) {
                return "https://www.sec.gov/Archives/edgar/data/1318605/0001/tsla-20260331.htm";
            }

            @Override
            String fetchAndCleanHtml(String docUrl) throws IOException {
                fetchCount.incrementAndGet();
                fetchEntered.countDown();
                try {
                    releaseFetch.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException(e);
                }
                return "clean filing content";
            }
        };

        CopyOnWriteArrayList<String> results = new CopyOnWriteArrayList<>();

        Thread first = new Thread(() -> {
            try {
                results.add(service.getLatestFilingContent("AAPL").block());
            } catch (Throwable t) {
                failure.set(t);
            }
        });
        Thread second = new Thread(() -> {
            try {
                results.add(service.getLatestFilingContent("AAPL").block());
            } catch (Throwable t) {
                failure.set(t);
            }
        });

        first.start();
        second.start();

        assertTrue(fetchEntered.await(5, TimeUnit.SECONDS));
        assertTrue(subscriptionsObserved.await(5, TimeUnit.SECONDS));
        assertEquals(1, fetchCount.get());
        releaseFetch.countDown();

        first.join(5000);
        second.join(5000);

        assertNull(failure.get(), () -> "Unexpected failure: " + failure.get());
        assertEquals(2, results.size());
        assertEquals("clean filing content", results.get(0));
        assertEquals("clean filing content", results.get(1));
        assertEquals(1, fetchCount.get());
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
