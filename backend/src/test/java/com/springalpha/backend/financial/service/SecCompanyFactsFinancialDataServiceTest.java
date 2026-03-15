package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class SecCompanyFactsFinancialDataServiceTest {

    @Test
    void buildsQuarterlyFactsFromSubmissionsAndCompanyFacts() {
        SecCompanyFactsFinancialDataService service = serviceForMetaQuarter();

        FinancialFacts facts = service.getFinancialFacts("META", "quarterly");

        assertNotNull(facts);
        assertEquals("Meta Platforms, Inc.", facts.getCompanyName());
        assertEquals("FY2026 Q1", facts.getPeriod());
        assertEquals("2026-04-24", facts.getFilingDate());
        assertEquals(new BigDecimal("42000000000"), facts.getRevenue());
        assertEquals(new BigDecimal("0.1667"), facts.getRevenueYoY());
        assertEquals(new BigDecimal("0.3095"), facts.getNetMargin());
        assertEquals(new BigDecimal("0.0574"), facts.getDebtToEquityRatio());
        assertEquals("USD", facts.getCurrency());
    }

    @Test
    void buildsQuarterlyHistoryFromRecentSecFilings() {
        SecCompanyFactsFinancialDataService service = serviceForMetaQuarter();

        List<HistoricalDataPoint> history = service.getHistoricalData("META", "quarterly");

        assertEquals(2, history.size());
        assertEquals("FY2025 Q1", history.get(0).getPeriod());
        assertEquals("FY2026 Q1", history.get(1).getPeriod());
        assertEquals(new BigDecimal("36000000000"), history.get(0).getRevenue());
        assertEquals(new BigDecimal("42000000000"), history.get(1).getRevenue());
    }

    @Test
    void derivesGrossMarginFromCostOfServicesWhenGrossProfitTagIsMissing() {
        SecCompanyFactsFinancialDataService service = serviceForOracleQuarterUsingCostOfServices();

        FinancialFacts facts = service.getFinancialFacts("ORCL", "quarterly");

        assertNotNull(facts);
        assertEquals("Oracle Corporation", facts.getCompanyName());
        assertEquals(new BigDecimal("14130000000"), facts.getRevenue());
        assertEquals(new BigDecimal("11300000000"), facts.getGrossProfit());
        assertEquals(new BigDecimal("0.7997"), facts.getGrossMargin());
        assertNull(facts.getRevenueYoY());
    }

    @Test
    void resolvesDotTickersThroughDashAliasesInSecDirectory() {
        SecCompanyFactsFinancialDataService service = serviceForBerkshireAlias();

        FinancialFacts facts = service.getFinancialFacts("BRK.B", "quarterly");

        assertNotNull(facts);
        assertEquals("Berkshire Hathaway Inc. Class B", facts.getCompanyName());
        assertEquals("FY2026 Q1", facts.getPeriod());
        assertEquals(new BigDecimal("95000000000"), facts.getRevenue());
    }

    private SecCompanyFactsFinancialDataService serviceForMetaQuarter() {
        return new SecCompanyFactsFinancialDataService(
                newStubClient(Map.of(
                        "/submissions/CIK0001326801.json", stubJson(200, """
                                {
                                  "ticker": "META",
                                  "name": "Meta Platforms, Inc.",
                                  "filings": {
                                    "recent": {
                                      "form": ["10-Q", "10-Q", "10-K"],
                                      "accessionNumber": ["0001326801-26-000001", "0001326801-25-000001", "0001326801-26-000099"],
                                      "filingDate": ["2026-04-24", "2025-04-25", "2026-01-29"],
                                      "reportDate": ["2026-03-31", "2025-03-31", "2025-12-31"]
                                    }
                                  }
                                }
                                """),
                        "/api/xbrl/companyfacts/CIK0001326801.json", stubJson(200, """
                                {
                                  "entityName": "Meta Platforms, Inc.",
                                  "facts": {
                                    "us-gaap": {
                                      "RevenueFromContractWithCustomerExcludingAssessedTax": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 36000000000
                                            },
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 42000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 36000000000
                                            }
                                          ]
                                        }
                                      },
                                      "GrossProfit": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 33700000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 28500000000
                                            }
                                          ]
                                        }
                                      },
                                      "OperatingIncomeLoss": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 17500000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 14300000000
                                            }
                                          ]
                                        }
                                      },
                                      "NetIncomeLoss": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 13000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 11000000000
                                            }
                                          ]
                                        }
                                      },
                                      "EarningsPerShareDiluted": {
                                        "units": {
                                          "USD/shares": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 5.21
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 4.31
                                            }
                                          ]
                                        }
                                      },
                                      "Assets": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "end": "2026-03-31",
                                              "val": 275000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "end": "2025-03-31",
                                              "val": 245000000000
                                            }
                                          ]
                                        }
                                      },
                                      "Liabilities": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "end": "2026-03-31",
                                              "val": 100000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "end": "2025-03-31",
                                              "val": 92000000000
                                            }
                                          ]
                                        }
                                      },
                                      "StockholdersEquity": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "end": "2026-03-31",
                                              "val": 175000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "end": "2025-03-31",
                                              "val": 153000000000
                                            }
                                          ]
                                        }
                                      },
                                      "LongTermDebtCurrent": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "end": "2026-03-31",
                                              "val": 4000000000
                                            }
                                          ]
                                        }
                                      },
                                      "LongTermDebtNoncurrent": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "end": "2026-03-31",
                                              "val": 6050000000
                                            }
                                          ]
                                        }
                                      },
                                      "NetCashProvidedByUsedInOperatingActivities": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 19000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": 15000000000
                                            }
                                          ]
                                        }
                                      },
                                      "PaymentsToAcquirePropertyPlantAndEquipment": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001326801-26-000001",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-04-24",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": -9000000000
                                            },
                                            {
                                              "accn": "0001326801-25-000001",
                                              "fy": 2025,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2025-04-25",
                                              "start": "2025-01-01",
                                              "end": "2025-03-31",
                                              "val": -7000000000
                                            }
                                          ]
                                        }
                                      }
                                    }
                                  }
                                }
                                """))),
                newStubClient(Map.of(
                        "/files/company_tickers.json", stubJson(200, """
                                {
                                  "0": {
                                    "cik_str": 1326801,
                                    "ticker": "META",
                                    "title": "Meta Platforms, Inc."
                                  }
                                }
                                """))),
                new FinancialCalculator(),
                null,
                Duration.ofHours(6),
                Duration.ofHours(24),
                Duration.ofHours(24));
    }

    private SecCompanyFactsFinancialDataService serviceForOracleQuarterUsingCostOfServices() {
        return new SecCompanyFactsFinancialDataService(
                newStubClient(Map.of(
                        "/submissions/CIK0001341439.json", stubJson(200, """
                                {
                                  "ticker": "ORCL",
                                  "name": "Oracle Corporation",
                                  "filings": {
                                    "recent": {
                                      "form": ["10-Q"],
                                      "accessionNumber": ["0001193125-26-101045"],
                                      "filingDate": ["2026-03-10"],
                                      "reportDate": ["2026-02-28"]
                                    }
                                  }
                                }
                                """),
                        "/api/xbrl/companyfacts/CIK0001341439.json", stubJson(200, """
                                {
                                  "entityName": "Oracle Corporation",
                                  "facts": {
                                    "us-gaap": {
                                      "RevenueFromContractWithCustomerExcludingAssessedTax": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "start": "2025-12-01",
                                              "end": "2026-02-28",
                                              "val": 14130000000
                                            }
                                          ]
                                        }
                                      },
                                      "CostOfServices": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "start": "2025-12-01",
                                              "end": "2026-02-28",
                                              "val": 2830000000
                                            }
                                          ]
                                        }
                                      },
                                      "OperatingIncomeLoss": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "start": "2025-12-01",
                                              "end": "2026-02-28",
                                              "val": 4360000000
                                            }
                                          ]
                                        }
                                      },
                                      "NetIncomeLoss": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "start": "2025-12-01",
                                              "end": "2026-02-28",
                                              "val": 2936000000
                                            }
                                          ]
                                        }
                                      },
                                      "Assets": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "end": "2026-02-28",
                                              "val": 163000000000
                                            }
                                          ]
                                        }
                                      },
                                      "Liabilities": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "end": "2026-02-28",
                                              "val": 145000000000
                                            }
                                          ]
                                        }
                                      },
                                      "StockholdersEquity": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0001193125-26-101045",
                                              "fy": 2026,
                                              "fp": "Q3",
                                              "form": "10-Q",
                                              "filed": "2026-03-10",
                                              "end": "2026-02-28",
                                              "val": 18000000000
                                            }
                                          ]
                                        }
                                      }
                                    }
                                  }
                                }
                                """))),
                newStubClient(Map.of(
                        "/files/company_tickers.json", stubJson(200, """
                                {
                                  "0": { "ticker": "ORCL", "cik_str": 1341439, "title": "Oracle Corporation" }
                                }
                                """))),
                new FinancialCalculator(),
                null,
                Duration.ofHours(6),
                Duration.ofHours(24),
                Duration.ofHours(24));
    }

    private SecCompanyFactsFinancialDataService serviceForBerkshireAlias() {
        return new SecCompanyFactsFinancialDataService(
                newStubClient(Map.of(
                        "/submissions/CIK0001067983.json", stubJson(200, """
                                {
                                  "ticker": "BRK-B",
                                  "name": "Berkshire Hathaway Inc. Class B",
                                  "filings": {
                                    "recent": {
                                      "form": ["10-Q"],
                                      "accessionNumber": ["0000950123-26-007654"],
                                      "filingDate": ["2026-05-05"],
                                      "reportDate": ["2026-03-31"]
                                    }
                                  }
                                }
                                """),
                        "/api/xbrl/companyfacts/CIK0001067983.json", stubJson(200, """
                                {
                                  "entityName": "Berkshire Hathaway Inc. Class B",
                                  "facts": {
                                    "us-gaap": {
                                      "Revenues": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0000950123-26-007654",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-05-05",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 95000000000
                                            }
                                          ]
                                        }
                                      },
                                      "NetIncomeLoss": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0000950123-26-007654",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-05-05",
                                              "start": "2026-01-01",
                                              "end": "2026-03-31",
                                              "val": 12000000000
                                            }
                                          ]
                                        }
                                      },
                                      "Assets": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0000950123-26-007654",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-05-05",
                                              "end": "2026-03-31",
                                              "val": 1200000000000
                                            }
                                          ]
                                        }
                                      },
                                      "Liabilities": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0000950123-26-007654",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-05-05",
                                              "end": "2026-03-31",
                                              "val": 700000000000
                                            }
                                          ]
                                        }
                                      },
                                      "StockholdersEquity": {
                                        "units": {
                                          "USD": [
                                            {
                                              "accn": "0000950123-26-007654",
                                              "fy": 2026,
                                              "fp": "Q1",
                                              "form": "10-Q",
                                              "filed": "2026-05-05",
                                              "end": "2026-03-31",
                                              "val": 500000000000
                                            }
                                          ]
                                        }
                                      }
                                    }
                                  }
                                }
                                """))),
                newStubClient(Map.of(
                        "/files/company_tickers.json", stubJson(200, """
                                {
                                  "0": {
                                    "cik_str": 1067983,
                                    "ticker": "BRK-B",
                                    "title": "Berkshire Hathaway Inc. Class B"
                                  }
                                }
                                """))),
                new FinancialCalculator(),
                null,
                Duration.ofHours(6),
                Duration.ofHours(24),
                Duration.ofHours(24));
    }

    private WebClient newStubClient(Map<String, StubResponse> routes) {
        ExchangeFunction exchangeFunction = request -> {
            StubResponse response = routes.get(request.url().getPath() +
                    (request.url().getQuery() == null ? "" : "?" + request.url().getQuery()));
            if (response == null) {
                return Mono.just(ClientResponse.create(HttpStatusCode.valueOf(404)).build());
            }
            return Mono.just(ClientResponse.create(HttpStatusCode.valueOf(response.status()))
                    .header("Content-Type", "application/json")
                    .body(response.body())
                    .build());
        };
        return WebClient.builder().baseUrl("https://example.com").exchangeFunction(exchangeFunction).build();
    }

    private static StubResponse stubJson(int status, String body) {
        return new StubResponse(status, body);
    }

    private record StubResponse(int status, String body) {
    }
}
