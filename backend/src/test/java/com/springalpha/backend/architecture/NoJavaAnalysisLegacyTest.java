package com.springalpha.backend.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertFalse;

class NoJavaAnalysisLegacyTest {

    private static final Path PROJECT_ROOT = Path.of("").toAbsolutePath();

    @Test
    void backendDoesNotContainJavaRagOrSpringAiAnalysisPath() throws IOException {
        List<Path> forbiddenPaths = List.of(
                PROJECT_ROOT.resolve("src/main/java/com/springalpha/backend/service/rag"),
                PROJECT_ROOT.resolve("src/test/java/com/springalpha/backend/service/rag"),
                PROJECT_ROOT.resolve("src/main/java/com/springalpha/backend/service/profile"),
                PROJECT_ROOT.resolve("src/test/java/com/springalpha/backend/service/profile"),
                PROJECT_ROOT.resolve("src/main/java/com/springalpha/backend/service/signals"),
                PROJECT_ROOT.resolve("src/test/java/com/springalpha/backend/service/signals"));

        for (Path forbiddenPath : forbiddenPaths) {
            assertFalse(Files.exists(forbiddenPath), () -> "Forbidden Java analysis path remains: " + forbiddenPath);
        }

        List<String> forbiddenNeedles = List.of(
                "org.springframework.ai",
                "spring-ai",
                "spring.ai",
                "vectorstore",
                "embedding-provider",
                "PgVectorStoreAutoConfiguration",
                "CompanyProfileSnapshot",
                "CompanyProfileExtractor",
                "BusinessSignalSnapshot",
                "BusinessSignalExtractor");

        try (Stream<Path> files = Files.walk(PROJECT_ROOT)) {
            List<Path> scannedFiles = files
                    .filter(Files::isRegularFile)
                    .filter(path -> path.startsWith(PROJECT_ROOT.resolve("src/main"))
                            || path.startsWith(PROJECT_ROOT.resolve("pom.xml")))
                    .filter(path -> !path.toString().contains("/target/"))
                    .toList();

            for (Path file : scannedFiles) {
                String content = Files.readString(file);
                for (String forbiddenNeedle : forbiddenNeedles) {
                    assertFalse(content.contains(forbiddenNeedle),
                            () -> "Forbidden Java analysis residue `" + forbiddenNeedle + "` remains in " + file);
                }
            }
        }
    }
}
