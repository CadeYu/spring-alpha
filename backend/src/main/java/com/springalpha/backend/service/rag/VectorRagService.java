package com.springalpha.backend.service.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Vector RAG Service - 使用 PGVector 进行语义搜索
 * 
 * 替代原有的关键词 RAG，通过向量相似度检索相关财报内容
 */
@Slf4j
@Service
public class VectorRagService {

    private static final int TOP_K = 5;
    private static final double SIMILARITY_THRESHOLD = 0.7;
    private static final int CHUNK_SIZE = 1000;
    private static final int CHUNK_OVERLAP = 200;

    private final VectorStore vectorStore;

    public VectorRagService(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
        log.info("✅ VectorRagService initialized with PGVector store");
    }

    /**
     * 存储财报文档到向量数据库
     */
    public void storeDocument(String ticker, String content) {
        log.info("📥 Storing document for ticker: {} ({} chars)", ticker, content.length());

        List<String> chunks = splitIntoChunks(content);
        log.debug("Split into {} chunks", chunks.size());

        List<Document> documents = chunks.stream()
                .map(chunk -> new Document(chunk, Map.of(
                        "ticker", ticker,
                        "source", "sec-10k")))
                .collect(Collectors.toList());

        vectorStore.add(documents);
        log.info("✅ Stored {} document chunks for {}", documents.size(), ticker);
    }

    /**
     * 根据查询检索相关上下文
     */
    public String retrieveRelevantContext(String ticker, String query) {
        log.info("🔍 Searching for: '{}' in ticker: {}", query, ticker);

        SearchRequest searchRequest = SearchRequest.builder()
                .query(query)
                .topK(TOP_K)
                .similarityThreshold(SIMILARITY_THRESHOLD)
                .filterExpression("ticker == '" + ticker + "'")
                .build();

        List<Document> results = vectorStore.similaritySearch(searchRequest);

        if (results.isEmpty()) {
            log.warn("No relevant documents found for query: {}", query);
            return "";
        }

        log.info("📄 Found {} relevant chunks", results.size());

        return results.stream()
                .map(Document::getFormattedContent)
                .collect(Collectors.joining("\n\n---\n\n"));
    }

    /**
     * 检查是否已存储该 ticker 的文档
     */
    public boolean hasDocuments(String ticker) {
        SearchRequest searchRequest = SearchRequest.builder()
                .query("financial report")
                .topK(1)
                .filterExpression("ticker == '" + ticker + "'")
                .build();

        return !vectorStore.similaritySearch(searchRequest).isEmpty();
    }

    /**
     * 将文本分割成重叠的块
     */
    private List<String> splitIntoChunks(String text) {
        List<String> chunks = new java.util.ArrayList<>();

        if (text == null || text.isEmpty()) {
            return chunks;
        }

        int start = 0;
        while (start < text.length()) {
            int end = Math.min(start + CHUNK_SIZE, text.length());

            // Try to break at sentence boundary
            if (end < text.length()) {
                int lastPeriod = text.lastIndexOf(". ", end);
                if (lastPeriod > start + CHUNK_SIZE / 2) {
                    end = lastPeriod + 1;
                }
            }

            chunks.add(text.substring(start, end).trim());
            start = end - CHUNK_OVERLAP;

            if (start >= text.length())
                break;
        }

        return chunks;
    }
}
