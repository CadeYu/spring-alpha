package com.springalpha.backend.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;

class BackendLoggingPolicyTest {

    @Test
    void productionLogsDoNotPrintCitationExcerpts() throws IOException {
        Path sourceRoot = Path.of("src/main/java");

        List<String> violations;
        try (Stream<Path> paths = Files.walk(sourceRoot)) {
            violations = paths
                    .filter(path -> path.toString().endsWith(".java"))
                    .flatMap(this::readLines)
                    .filter(line -> line.contains("log.") && line.contains("getExcerpt()"))
                    .toList();
        }

        assertThat(violations).isEmpty();
    }

    @Test
    void sourceCommentsStayEnglishInFinancialBoundaryModels() throws IOException {
        List<Path> files = List.of(
                Path.of("src/main/java/com/springalpha/backend/financial/model/FinancialFacts.java"),
                Path.of("src/main/java/com/springalpha/backend/financial/model/IncomeStatement.java"),
                Path.of("src/main/java/com/springalpha/backend/financial/model/BalanceSheet.java"),
                Path.of("src/main/java/com/springalpha/backend/financial/model/CashFlowStatement.java"),
                Path.of("src/main/java/com/springalpha/backend/financial/service/FinancialDataService.java"),
                Path.of("src/main/java/com/springalpha/backend/service/SecService.java"),
                Path.of("src/main/java/com/springalpha/backend/SpringAlphaApplication.java"));

        List<String> nonAsciiLines = files.stream()
                .flatMap(this::readLines)
                .filter(line -> line.codePoints().anyMatch(codePoint -> codePoint > 127))
                .toList();

        assertThat(nonAsciiLines).isEmpty();
    }

    @Test
    void secServiceInfoLogsStayConcise() throws IOException {
        Path file = Path.of("src/main/java/com/springalpha/backend/service/SecService.java");

        List<String> violations = readLines(file)
                .filter(line -> line.contains("log.info"))
                .filter(line -> line.contains("Url") || line.contains("URL") || line.contains("docUrl")
                        || line.contains("indexUrl"))
                .toList();

        assertThat(violations).isEmpty();
    }

    private Stream<String> readLines(Path path) {
        try {
            return Files.readAllLines(path).stream().map(line -> path + ": " + line.trim());
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read " + path, e);
        }
    }
}
