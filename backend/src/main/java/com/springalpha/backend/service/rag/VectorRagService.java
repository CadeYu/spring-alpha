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
 * Vector RAG Service - 向量增强检索服务
 * <p>
 * 这是 RAG (Retrieval-Augmented Generation) 的核心引擎。
 * 它负责连接此时此刻的 "User Query" 和浩瀚的 "SEC 10-K Document"。
 * <p>
 * **核心流程**:
 * 1. **Ingestion (入库)**: 把 10MB 的文本切成小块 (Chunking)，算成向量，存入 PGVector。
 * 2. **Retrieval (检索)**: 当用户问 "为什么亏损" 时，把这个问题也变成向量，去数据库里找最相似的 5 个片段。
 */
@Slf4j
@Service
public class VectorRagService {

    // 只取最相关的 5 个片段，大约 2000-3000 tokens，刚好填满 LLM 的上下文窗口，又不会太贵
    private static final int TOP_K = 5;

    // 相似度阈值 (0.0 - 1.0)。
    // 降低到 0.4 是为了提高"召回率" (Recall)，即使措辞不完全一样也能搜到。
    // 比如：Query="risk" 能搜到 Content="uncertainty"
    private static final double SIMILARITY_THRESHOLD = 0.4;

    // 每个切片的大小 (字符数)。3000 chars ≈ 700 tokens。
    private static final int CHUNK_SIZE = 3000;

    // 切片重叠部分，防止一句话被切断导致语义丢失。
    private static final int CHUNK_OVERLAP = 300;

    // 限制最大切片数，防止一篇超长文档把数据库撑爆，或者 Embedding API 超时。
    private static final int MAX_CHUNKS = 30;

    private final VectorStore vectorStore;

    public VectorRagService(VectorStore vectorStore) {
        this.vectorStore = vectorStore;
        log.info("✅ VectorRagService initialized with PGVector store");
    }

    /**
     * 存储财报文档到向量数据库
     * <p>
     * 这是一个 **耗时操作** (Embedding API 调用 + DB 写入)，通常异步执行。
     * 
     * @param ticker  股票代码
     * @param content 清洗后的 SEC 10-K 文本 (Markdown 格式)
     */
    public void storeDocument(String ticker, String content) {
        log.info("📥 Storing document for ticker: {} ({} chars)", ticker, content.length());

        // 1. 切片 (Chunking): 把大象放进冰箱的第一步，把文本切碎
        List<String> chunks = splitIntoChunks(content);
        log.info("✂️ Split into {} chunks (CHUNK_SIZE={}, MAX_CHUNKS={})", chunks.size(), CHUNK_SIZE, MAX_CHUNKS);

        // 2. 包装 (Wrapping): 把文本块包装成 Document 对象，并打上 Metadata 标签(ticker)
        // 这样检索时可以通过 metadata filter 只搜特定公司的文档
        List<Document> documents = chunks.stream()
                .map(chunk -> new Document(chunk, Map.of(
                        "ticker", ticker,
                        "source", "sec-10k")))
                .collect(Collectors.toList());

        log.info("🔢 Calling vectorStore.add() with {} documents. This will generate embeddings (may take a while)...",
                documents.size());

        // 3. 向量化与存储 (Embedding & Upsert):
        // 这里会调用 EmbeddingModel (Gemini/OpenAI) 把文本变成向量
        // 然后存入 Postgres 的 vector 字段
        long startTime = System.currentTimeMillis();
        vectorStore.add(documents);

        long elapsed = System.currentTimeMillis() - startTime;
        log.info("✅ Stored {} document chunks for {} in {} ms", documents.size(), ticker, elapsed);
    }

    /**
     * 语义检索 (Semantic Search)
     * <p>
     * 这是 RAG 的 "Retrieve" 步骤。
     * 它不仅仅是关键词匹配 (Keyword Match)，而是理解语义。
     * 
     * @param ticker 股票代码 (作为 Filter)
     * @param query  用户的问题 (e.g., "What are the revenue drivers?")
     * @return 拼接好的相关文本片段，用作 Prompt 的 context
     */
    public String retrieveRelevantContext(String ticker, String query) {
        log.info("🔍 Searching for: '{}' in ticker: {}", query, ticker);

        SearchRequest searchRequest = SearchRequest.builder()
                .query(query)
                .topK(TOP_K) // 只我们要最相关的 K 个
                .similarityThreshold(SIMILARITY_THRESHOLD) // 过滤掉不相关的噪音
                .filterExpression("ticker == '" + ticker + "'") // 关键：只在当前股票的文档里搜！
                .build();

        List<Document> results = vectorStore.similaritySearch(searchRequest);

        if (results.isEmpty()) {
            log.warn("No relevant documents found for query: {}", query);
            return "";
        }

        log.info("📄 Found {} relevant chunks", results.size());

        // 将搜到的片段用分隔符拼起来，喂给 LLM
        return results.stream()
                .map(Document::getFormattedContent)
                .collect(Collectors.joining("\n\n---\n\n"));
    }

    /**
     * 检查是否已存储该 ticker 的文档 (幂等性检查)
     * 防止重复处理同一个文件
     */
    public boolean hasDocuments(String ticker) {
        // 随便搜一个词，看看有没有结果，有就是存过了
        SearchRequest searchRequest = SearchRequest.builder()
                .query("financial report")
                .topK(1)
                .filterExpression("ticker == '" + ticker + "'")
                .build();

        return !vectorStore.similaritySearch(searchRequest).isEmpty();
    }

    /**
     * 递归切片算法 (Simple Recursive Splitter)
     * <p>
     * 尽量在句子结束符 (. ) 处切分，保持语义完整。
     */
    private List<String> splitIntoChunks(String text) {
        List<String> chunks = new java.util.ArrayList<>();

        if (text == null || text.isEmpty()) {
            return chunks;
        }

        int start = 0;
        while (start < text.length() && chunks.size() < MAX_CHUNKS) {
            int end = Math.min(start + CHUNK_SIZE, text.length());

            // 优化：尝试在句子句号处断句，而不是生硬地切断
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

            // 关键：确保 start 永远向前移动，防止死循环
            int nextStart = end - CHUNK_OVERLAP; // 制造重叠，保证上下文连贯
            if (nextStart <= start) {
                nextStart = start + 1; // 强制前进
            }
            start = nextStart;
        }

        if (chunks.size() >= MAX_CHUNKS) {
            log.warn("⚠️ Document truncated to {} chunks to prevent OOM", MAX_CHUNKS);
        }

        return chunks;
    }
}
