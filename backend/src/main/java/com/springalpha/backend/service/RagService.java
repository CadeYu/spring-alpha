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
    
    // Chunk 大小 (字符数)
    private static final int CHUNK_SIZE = 2000;
    // Chunk 重叠 (防止句子被截断)
    private static final int CHUNK_OVERLAP = 200;
    // 返回的 Top K 个最相关片段
    private static final int TOP_K = 5;
    // 最终上下文最大长度 (防止 Token 超限)
    private static final int MAX_CONTEXT_LENGTH = 15000;

    /**
     * 从长文本中检索与 query 最相关的内容片段
     * 
     * @param fullText  完整的 SEC 10-K 文本
     * @param query     用户查询或预设的检索关键词
     * @return          拼接后的相关上下文
     */
    public String retrieveRelevantContext(String fullText, String query) {
        log.info("📚 RAG 开始处理，原文长度: {} 字符", fullText.length());
        
        // 1. 分割文本为 chunks
        List<String> chunks = splitIntoChunks(fullText);
        log.info("📦 分割为 {} 个 chunks (size={}, overlap={})", chunks.size(), CHUNK_SIZE, CHUNK_OVERLAP);
        
        // 2. 简单的关键词匹配评分
        List<String> queryTerms = extractQueryTerms(query);
        log.info("🔑 检索关键词: {}", queryTerms);
        
        // 3. 计算每个 chunk 的相关性得分
        List<ScoredChunk> scoredChunks = new ArrayList<>();
        for (int i = 0; i < chunks.size(); i++) {
            String chunk = chunks.get(i);
            double score = calculateRelevanceScore(chunk, queryTerms);
            scoredChunks.add(new ScoredChunk(i, chunk, score));
        }
        
        // 4. 按得分排序，取 Top K
        scoredChunks.sort((a, b) -> Double.compare(b.score, a.score));
        List<ScoredChunk> topChunks = scoredChunks.subList(0, Math.min(TOP_K, scoredChunks.size()));
        
        // 5. 按原始顺序排列 (保持文档结构)
        topChunks.sort(Comparator.comparingInt(c -> c.index));
        
        // 6. 拼接结果
        StringBuilder context = new StringBuilder();
        for (ScoredChunk sc : topChunks) {
            if (context.length() + sc.text.length() > MAX_CONTEXT_LENGTH) {
                break;
            }
            context.append(sc.text).append("\n\n---\n\n");
        }
        
        String result = context.toString().trim();
        log.info("✅ RAG 检索完成，返回上下文长度: {} 字符 (Top {} chunks)", result.length(), topChunks.size());
        
        return result;
    }

    /**
     * 将长文本分割成重叠的 chunks
     */
    private List<String> splitIntoChunks(String text) {
        List<String> chunks = new ArrayList<>();
        int start = 0;
        
        while (start < text.length()) {
            int end = Math.min(start + CHUNK_SIZE, text.length());
            
            // 尝试在句号或换行处断开，避免截断句子
            if (end < text.length()) {
                int lastPeriod = text.lastIndexOf(". ", end);
                int lastNewline = text.lastIndexOf("\n", end);
                int breakPoint = Math.max(lastPeriod, lastNewline);
                
                if (breakPoint > start + CHUNK_SIZE / 2) {
                    end = breakPoint + 1;
                }
            }
            
            chunks.add(text.substring(start, end).trim());
            start = end - CHUNK_OVERLAP;
            
            if (start < 0) start = 0;
        }
        
        return chunks;
    }

    /**
     * 提取查询中的关键词
     */
    private List<String> extractQueryTerms(String query) {
        // 简单实现：按逗号和空格分割，转小写
        String[] terms = query.toLowerCase()
                .replaceAll("[^a-zA-Z0-9,\\s]", "")
                .split("[,\\s]+");
        
        // 过滤掉常见停用词
        Set<String> stopWords = Set.of("the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with");
        List<String> result = new ArrayList<>();
        for (String term : terms) {
            if (term.length() > 2 && !stopWords.contains(term)) {
                result.add(term);
            }
        }
        return result;
    }

    /**
     * 计算 chunk 与查询的相关性得分 (简单的 TF 匹配)
     */
    private double calculateRelevanceScore(String chunk, List<String> queryTerms) {
        String lowerChunk = chunk.toLowerCase();
        double score = 0.0;
        
        for (String term : queryTerms) {
            // 计算词频
            int count = countOccurrences(lowerChunk, term);
            if (count > 0) {
                // 使用 log 避免某个词出现太多次主导评分
                score += Math.log(1 + count);
            }
        }
        
        // 对包含关键财务术语的 chunk 加分
        String[] bonusTerms = {"revenue", "income", "profit", "loss", "risk", "guidance", "outlook", "growth"};
        for (String bonus : bonusTerms) {
            if (lowerChunk.contains(bonus)) {
                score += 0.5;
            }
        }
        
        return score;
    }

    /**
     * 统计子串出现次数
     */
    private int countOccurrences(String text, String sub) {
        int count = 0;
        int idx = 0;
        while ((idx = text.indexOf(sub, idx)) != -1) {
            count++;
            idx += sub.length();
        }
        return count;
    }

    /**
     * 带评分的 Chunk 内部类
     */
    private static class ScoredChunk {
        int index;
        String text;
        double score;

        ScoredChunk(int index, String text, double score) {
            this.index = index;
            this.text = text;
            this.score = score;
        }
    }
}
