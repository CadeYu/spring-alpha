#!/bin/bash
# 验证 Spring Alpha Backend 功能

echo "======================================"
echo "🧪 Spring Alpha Backend 验证脚本"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="http://localhost:8081"

# Test 1: Health Check
echo "📌 Test 1: Health Check"
RESPONSE=$(curl -s "$BASE_URL/health")
if [[ $RESPONSE == *"UP"* ]]; then
    echo -e "${GREEN}✅ Health check passed${NC}"
else
    echo -e "${RED}❌ Health check failed${NC}"
fi
echo ""

# Test 2: 获取财务数据
echo "📌 Test 2: 获取财务数据 (AAPL)"
RESPONSE=$(curl -s "$BASE_URL/api/financial/AAPL")
REVENUE=$(echo $RESPONSE | jq -r '.revenue // empty' 2>/dev/null)
TICKER=$(echo $RESPONSE | jq -r '.ticker // empty' 2>/dev/null)

if [[ -n "$REVENUE" && "$TICKER" == "AAPL" ]]; then
    echo -e "${GREEN}✅ Financial data API working${NC}"
    echo "   Ticker: $TICKER"
    echo "   Revenue: $REVENUE"
else
    echo -e "${RED}❌ Financial data API failed${NC}"
fi
echo ""

# Test 3: 支持的股票列表
echo "📌 Test 3: 支持的股票列表"
RESPONSE=$(curl -s "$BASE_URL/api/financial/supported")
COUNT=$(echo $RESPONSE | jq -r '.count // 0' 2>/dev/null)
TICKERS=$(echo $RESPONSE | jq -r '.supportedTickers[] // empty' 2>/dev/null | tr '\n' ', ')

if [[ $COUNT -gt 0 ]]; then
    echo -e "${GREEN}✅ Supported tickers: $TICKERS${NC}"
else
    echo -e "${RED}❌ Failed to get supported tickers${NC}"
fi
echo ""

# Test 4: Mock 分析报告（英文）
echo "📌 Test 4: Mock 分析报告 (AAPL - English)"
RESPONSE=$(curl -s "$BASE_URL/api/sec/analyze/AAPL?lang=en" | head -1)
SUMMARY=$(echo $RESPONSE | sed 's/^data://g' | jq -r '.executiveSummary // empty' 2>/dev/null | head -c 60)

if [[ -n "$SUMMARY" ]]; then
    echo -e "${GREEN}✅ Analysis API working (EN)${NC}"
    echo "   Summary: ${SUMMARY}..."
else
    echo -e "${RED}❌ Analysis API failed (EN)${NC}"
fi
echo ""

# Test 5: Mock 分析报告（中文）
echo "📌 Test 5: Mock 分析报告 (AAPL - 中文)"
RESPONSE=$(curl -s "$BASE_URL/api/sec/analyze/AAPL?lang=zh" | head -1)
SUMMARY=$(echo $RESPONSE | sed 's/^data://g' | jq -r '.executiveSummary // empty' 2>/dev/null | head -c 40)

if [[ -n "$SUMMARY" ]]; then
    echo -e "${GREEN}✅ Analysis API working (ZH)${NC}"
    echo "   摘要: ${SUMMARY}..."
else
    echo -e "${RED}❌ Analysis API failed (ZH)${NC}"
fi
echo ""

# Test 6: 检查加载的策略
echo "📌 Test 6: 检查后端日志中的策略"
echo -e "${YELLOW}ℹ️  检查后端终端输出中是否有:${NC}"
echo "   '🎯 Loaded AI strategies: [enhanced-mock, groq]'"
echo ""

echo "======================================"
echo "✨ 验证完成！"
echo "======================================"
echo ""
echo "下一步测试选项："
echo "1. 启动前端: cd frontend && npm run dev"
echo "2. 切换到 Groq 真实 LLM（需要 API Key）"
echo "3. 测试更多股票: curl $BASE_URL/api/financial/MSFT"
echo ""
