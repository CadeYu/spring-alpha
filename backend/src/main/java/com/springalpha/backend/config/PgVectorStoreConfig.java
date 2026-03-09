package com.springalpha.backend.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.ai.vectorstore.pgvector.PgVectorStore;
import org.springframework.ai.vectorstore.pgvector.autoconfigure.PgVectorStoreProperties;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * Custom PGVector store configuration that repairs dimension drift before the
 * store starts serving queries.
 */
@Slf4j
@Configuration
@EnableConfigurationProperties(PgVectorStoreProperties.class)
public class PgVectorStoreConfig {

    @Bean
    @ConditionalOnMissingBean(VectorStore.class)
    public VectorStore vectorStore(JdbcTemplate jdbcTemplate,
            EmbeddingModel embeddingModel,
            PgVectorStoreProperties properties) {
        int targetDimensions = properties.getDimensions();
        String currentEmbeddingType = resolveEmbeddingType(jdbcTemplate, properties);
        boolean tableExists = currentEmbeddingType != null;
        boolean shouldRecreate = tableExists && !("vector(" + targetDimensions + ")").equals(currentEmbeddingType);

        if (shouldRecreate) {
            log.warn("⚠️ Recreating PGVector table {}.{} because embedding type is {} but application expects vector({})",
                    properties.getSchemaName(), properties.getTableName(), currentEmbeddingType, targetDimensions);
        } else if (tableExists) {
            log.info("✅ PGVector table {}.{} already matches expected embedding type {}",
                    properties.getSchemaName(), properties.getTableName(), currentEmbeddingType);
        } else {
            log.info("ℹ️ PGVector table {}.{} does not exist yet and will be created with vector({})",
                    properties.getSchemaName(), properties.getTableName(), targetDimensions);
        }

        return PgVectorStore.builder(jdbcTemplate, embeddingModel)
                .schemaName(properties.getSchemaName())
                .vectorTableName(properties.getTableName())
                .idType(properties.getIdType())
                .dimensions(targetDimensions)
                .distanceType(properties.getDistanceType())
                .indexType(properties.getIndexType())
                .initializeSchema(properties.isInitializeSchema())
                .removeExistingVectorStoreTable(shouldRecreate)
                .vectorTableValidationsEnabled(properties.isSchemaValidation())
                .maxDocumentBatchSize(properties.getMaxDocumentBatchSize())
                .build();
    }

    private String resolveEmbeddingType(JdbcTemplate jdbcTemplate, PgVectorStoreProperties properties) {
        return jdbcTemplate.query("""
                SELECT format_type(a.atttypid, a.atttypmod) AS embedding_type
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = ?
                  AND c.relname = ?
                  AND a.attname = 'embedding'
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                """,
                ps -> {
                    ps.setString(1, properties.getSchemaName());
                    ps.setString(2, properties.getTableName());
                },
                rs -> rs.next() ? rs.getString("embedding_type") : null);
    }
}
