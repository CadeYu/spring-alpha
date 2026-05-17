package com.springalpha.backend.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.core.io.ClassPathResource;

class BackendProfileConfigTest {

    private final YamlPropertySourceLoader loader = new YamlPropertySourceLoader();

    @Test
    void commonConfigKeepsDatasourceCredentialsOutOfTheDefaultProfile() throws IOException {
        List<PropertySource<?>> sources = load("application.yml");

        assertThat(property(sources, "spring.profiles.active")).isEqualTo("${SPRING_PROFILES_ACTIVE:local}");
        assertThat(property(sources, "spring.datasource.driver-class-name")).isEqualTo("org.postgresql.Driver");
        assertThat(property(sources, "spring.datasource.url")).isNull();
        assertThat(property(sources, "spring.datasource.password")).isNull();
        assertThat(property(sources, "logging.level.root")).isEqualTo("INFO");
        assertThat(property(sources, "logging.level.com.springalpha")).isEqualTo("INFO");
    }

    @Test
    void localConfigOwnsDeveloperDatabaseDefaults() throws IOException {
        List<PropertySource<?>> sources = load("application-local.yml");

        assertThat(property(sources, "spring.datasource.url"))
                .isEqualTo("${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/spring_alpha}");
        assertThat(property(sources, "spring.datasource.username"))
                .isEqualTo("${SPRING_DATASOURCE_USERNAME:spring_alpha}");
        assertThat(property(sources, "spring.jpa.hibernate.ddl-auto"))
                .isEqualTo("${SPRING_JPA_HIBERNATE_DDL_AUTO:update}");
        assertThat(property(sources, "logging.level.com.springalpha"))
                .isEqualTo("${SPRING_ALPHA_LOG_LEVEL:DEBUG}");
    }

    @Test
    void composeConfigUsesServiceDnsAndConservativeLogs() throws IOException {
        List<PropertySource<?>> sources = load("application-compose.yml");

        assertThat(property(sources, "spring.datasource.url"))
                .isEqualTo("${SPRING_DATASOURCE_URL:jdbc:postgresql://pgvector:5432/spring_alpha}");
        assertThat(property(sources, "spring.jpa.hibernate.ddl-auto"))
                .isEqualTo("${SPRING_JPA_HIBERNATE_DDL_AUTO:update}");
        assertThat(property(sources, "logging.level.com.springalpha"))
                .isEqualTo("${SPRING_ALPHA_LOG_LEVEL:INFO}");
    }

    @Test
    void prodConfigRequiresRuntimeDatasourceAndUsesValidateDdl() throws IOException {
        List<PropertySource<?>> sources = load("application-prod.yml");

        assertThat(property(sources, "spring.datasource.url")).isEqualTo("${SPRING_DATASOURCE_URL}");
        assertThat(property(sources, "spring.datasource.username")).isEqualTo("${SPRING_DATASOURCE_USERNAME}");
        assertThat(property(sources, "spring.datasource.password")).isEqualTo("${SPRING_DATASOURCE_PASSWORD}");
        assertThat(property(sources, "spring.jpa.hibernate.ddl-auto"))
                .isEqualTo("${SPRING_JPA_HIBERNATE_DDL_AUTO:validate}");
        assertThat(property(sources, "logging.level.com.springalpha"))
                .isEqualTo("${SPRING_ALPHA_LOG_LEVEL:INFO}");
    }

    @Test
    void prodConfigAcceptsSupabasePoolerJdbcUrlFromRuntimeEnvironment() {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new MapPropertySource(
                "test-env",
                java.util.Map.of(
                        "SPRING_DATASOURCE_URL",
                        "jdbc:postgresql://aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require",
                        "SPRING_DATASOURCE_USERNAME",
                        "postgres.agwipsqljlgcnsispndc",
                        "SPRING_DATASOURCE_PASSWORD",
                        "runtime-only-password")));

        String url = environment.getRequiredProperty("SPRING_DATASOURCE_URL");
        String username = environment.getRequiredProperty("SPRING_DATASOURCE_USERNAME");

        assertThat(url).contains("pooler.supabase.com:5432/postgres?sslmode=require");
        assertThat(username).isEqualTo("postgres.agwipsqljlgcnsispndc");
    }

    private List<PropertySource<?>> load(String resourceName) throws IOException {
        return loader.load(resourceName, new ClassPathResource(resourceName));
    }

    private Object property(List<PropertySource<?>> sources, String key) {
        return sources.stream()
                .map(source -> source.getProperty(key))
                .filter(value -> value != null)
                .findFirst()
                .orElse(null);
    }
}
