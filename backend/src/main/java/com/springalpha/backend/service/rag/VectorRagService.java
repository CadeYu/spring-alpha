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
    private static final double SIMILARITY_THRESHOLD = 0.4; // Lowered from 0.7 for better recall with 3072-dim model
    private static final int CHUNK_SIZE = 3000; // Larger chunks = fewer API calls
    private static final int CHUNK_OVERLAP = 300;
    private static final int MAX_CHUNKS = 30; // Limit total chunks

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
        log.info("✂️ Split into {} chunks (CHUNK_SIZE={}, MAX_CHUNKS={})", chunks.size(), CHUNK_SIZE, MAX_CHUNKS);

        List<Document> documents = chunks.stream()
                .map(chunk -> new Document(chunk, Map.of(
                        "ticker", ticker,
                        "source", "sec-10k")))
                .collect(Collectors.toList());

        log.info("🔢 Calling vectorStore.add() with {} documents. This will generate embeddings (may take a while)...",
                documents.size());
        long startTime = System.currentTimeMillis();

        vectorStore.add(documents);

        long elapsed = System.currentTimeMillis() - startTime;
        log.info("✅ Stored {} document chunks for {} in {} ms", documents.size(), ticker, elapsed);
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
        while (start < text.length() && chunks.size() < MAX_CHUNKS) {
            int end = Math.min(start + CHUNK_SIZE, text.length());

            // Try to break at sentence boundary
            if (end < text.length()) {
                int lastPeriod = text.lastIndexOf(". ", end);
                if (lastPeriod > start + CHUNK_SIZE / 2) {
                    end = lastPeriod + 1;
                }
            }

            String chunk = text.substring(start, end).trim();
            if (!chunk.isEmpty()) {
                chunks.add(chunk);
            }

            // CRITICAL: Ensure start always moves forward to prevent infinite loop
            int nextStart = end - CHUNK_OVERLAP;
            if (nextStart <= start) {
                nextStart = start + 1; // Force forward progress
            }
            start = nextStart;
        }

        if (chunks.size() >= MAX_CHUNKS) {
            log.warn("⚠️ Document truncated to {} chunks to prevent OOM", MAX_CHUNKS);
        }

        return chunks;
    }
}
