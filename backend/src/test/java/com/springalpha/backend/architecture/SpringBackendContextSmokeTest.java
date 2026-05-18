package com.springalpha.backend.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.financial.service.HybridFinancialDataService;
import com.springalpha.backend.financial.service.MarketEnrichmentService;
import com.springalpha.backend.financial.service.SecCompanyFactsFinancialDataService;
import com.springalpha.backend.financial.service.YahooFinanceMarketDataService;
import com.springalpha.backend.service.research.ResearchAgentClient;
import com.springalpha.backend.service.research.ResearchServiceAgentClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:spring_backend_context_smoke;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.jpa.show-sql=false",
        "app.research-service.base-url=http://127.0.0.1:1"
})
@ActiveProfiles("test")
class SpringBackendContextSmokeTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void startsWithExpectedDatasourceAndAgentBeansOnly() {
        Map<String, FinancialDataService> financialServices = context.getBeansOfType(FinancialDataService.class);

        assertThat(context.getBean(FinancialDataService.class)).isInstanceOf(HybridFinancialDataService.class);
        assertThat(financialServices)
                .containsEntry("hybridFinancialDataService", context.getBean(HybridFinancialDataService.class))
                .containsEntry("secCompanyFactsFinancialDataService",
                        context.getBean(SecCompanyFactsFinancialDataService.class));
        assertThat(financialServices.keySet())
                .doesNotContain("fmpFinancialDataService", "javaLegacyAnalysisService");

        assertThat(context.getBean(MarketEnrichmentService.class)).isInstanceOf(YahooFinanceMarketDataService.class);
        assertThat(context.getBean(ResearchAgentClient.class)).isInstanceOf(ResearchServiceAgentClient.class);
    }
}
