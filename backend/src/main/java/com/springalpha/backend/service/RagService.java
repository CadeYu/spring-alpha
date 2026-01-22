package com.springalpha.backend.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * 简易 RAG (Retrieval-Augmented Generation) 服务
 * 
 * 功能：将长文本分割成 chunks，基于关键词匹配检索最相关的片段
 * 
 * 注意：这是一个简化版实现，使用关键词匹配而非向量嵌入。
 * 生产环境建议集成 Spring AI 的 VectorStore (如 PGVector, Pinecone)。
 */
@Service
public class RagService {

    private static final Logger log = LoggerFactory.getLogger(RagService.class);
    
    // Chunk 大小 (字符数) - 增大以减少 chunk 数量
    private static final int CHUNK_SIZE = 4000;
    // Chunk 步进 (无重叠，简化逻辑)
    private static final int CHUNK_STEP = 3800;
    // 返回的 Top K 个最相关片段
    private static final int TOP_K = 4;
    // 最终上下文最大长度 (防止 Token 超限)
    private static final int MAX_CONTEXT_LENGTH = 12000;

    /**
     * 从长文本中检索与 query 最相关的内容片段
     * 
     * @param fullText  完整的 SEC 10-K 文本
     * @param query     用户查询或预设的检索关键词
     * @return          拼接后的相关上下文
     */
    public String retrieveRelevantContext(String fullText, String query) {
        log.info("📚 RAG 开始处理，原文长度: {} 字符", fullText.length());
        
        // 安全检查：如果文本太短，直接返回
        if (fullText.length() <= MAX_CONTEXT_LENGTH) {
            log.info("📦 文本长度小于上下文限制，直接返回全文");
            return fullText;
        }
        
        // 1. 分割文本为 chunks (内存优化版)
        List<ChunkInfo> chunkInfos = splitIntoChunksOptimized(fullText);
        log.info("📦 分割为 {} 个 chunks", chunkInfos.size());
        
        // 2. 提取查询关键词
        Set<String> queryTerms = extractQueryTerms(query);
        log.info("🔑 检索关键词: {}", queryTerms);
        
        // 3. 计算每个 chunk 的相关性得分 (不存储完整文本，只存储位置)
        List<ScoredChunk> scoredChunks = new ArrayList<>();
        for (ChunkInfo info : chunkInfos) {
            // 提取 chunk 文本用于评分
            String chunkText = fullText.substring(info.start, info.end);
            double score = calculateRelevanceScore(chunkText, queryTerms);
            scoredChunks.add(new ScoredChunk(info.index, info.start, info.end, score));
        }
        
        // 4. 按得分排序，取 Top K
        scoredChunks.sort((a, b) -> Double.compare(b.score, a.score));
        List<ScoredChunk> topChunks = new ArrayList<>(
            scoredChunks.subList(0, Math.min(TOP_K, scoredChunks.size()))
        );
        
        // 5. 按原始顺序排列 (保持文档结构)
        topChunks.sort(Comparator.comparingInt(c -> c.index));
        
        // 6. 拼接结果
        StringBuilder context = new StringBuilder();
        for (ScoredChunk sc : topChunks) {
            String chunkText = fullText.substring(sc.start, sc.end);
            if (context.length() + chunkText.length() > MAX_CONTEXT_LENGTH) {
                break;
            }
            context.append(chunkText).append("\n\n---\n\n");
        }
        
        String result = context.toString().trim();
        log.info("✅ RAG 检索完成，返回上下文长度: {} 字符 (Top {} chunks)", result.length(), topChunks.size());
        
        return result;
    }

    /**
     * 内存优化版分割 - 只存储位置信息，不存储完整文本
     */
    private List<ChunkInfo> splitIntoChunksOptimized(String text) {
        List<ChunkInfo> chunks = new ArrayList<>();
        int textLen = text.length();
        int index = 0;
        int start = 0;
        
        while (start < textLen) {
            int end = Math.min(start + CHUNK_SIZE, textLen);
            chunks.add(new ChunkInfo(index++, start, end));
            start += CHUNK_STEP;
        }
        
        return chunks;
    }

    /**
     * 提取查询中的关键词
     */
    private Set<String> extractQueryTerms(String query) {
        String[] terms = query.toLowerCase()
                .replaceAll("[^a-zA-Z0-9,\\s]", "")
                .split("[,\\s]+");
        
        Set<String> stopWords = Set.of("the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with");
        Set<String> result = new HashSet<>();
        for (String term : terms) {
            if (term.length() > 2 && !stopWords.contains(term)) {
                result.add(term);
            }
        }
        return result;
    }

    /**
     * 计算 chunk 与查询的相关性得分 (简单的关键词匹配)
     */
    private double calculateRelevanceScore(String chunk, Set<String> queryTerms) {
        String lowerChunk = chunk.toLowerCase();
        double score = 0.0;
        
        for (String term : queryTerms) {
            if (lowerChunk.contains(term)) {
                score += 1.0;
            }
        }
        
        // 对包含关键财务术语的 chunk 加分
        String[] bonusTerms = {"revenue", "income", "profit", "loss", "risk", "guidance", "outlook", "growth", "margin", "cash flow"};
        for (String bonus : bonusTerms) {
            if (lowerChunk.contains(bonus)) {
                score += 0.5;
            }
        }
        
        return score;
    }

    /**
     * Chunk 位置信息 (内存优化)
     */
    private static class ChunkInfo {
        int index;
        int start;
        int end;

        ChunkInfo(int index, int start, int end) {
            this.index = index;
            this.start = start;
            this.end = end;
        }
    }

    /**
     * 带评分的 Chunk (存储位置而非文本)
     */
    private static class ScoredChunk {
        int index;
        int start;
        int end;
        double score;

        ScoredChunk(int index, int start, int end, double score) {
            this.index = index;
            this.start = start;
            this.end = end;
            this.score = score;
        }
    }
}
