#!/bin/bash

# Copy this file to start_backend.sh and fill in your API keys
# start_backend.sh is gitignored and won't be committed

export GROQ_API_KEY=your_groq_api_key_here
export FMP_API_KEY=your_fmp_api_key_here
export NEON_PASSWORD=your_neon_password_here
# export GEMINI_API_KEY=your_gemini_api_key_here

# Increase JVM heap memory (prevents OOM when processing large SEC filings)
export MAVEN_OPTS="-Xms256m -Xmx1024m"

# Check and kill process occupying port 8081
echo "🔍 Checking port 8081..."
PID=$(lsof -ti:8081)
if [ ! -z "$PID" ]; then
  echo "⚠️  Port 8081 is occupied by PID: $PID"
  echo "🔪 Killing process..."
  kill -9 $PID
  sleep 1
  echo "✅ Port 8081 is now free"
else
  echo "✅ Port 8081 is available"
fi

echo "🚀 Starting Spring Alpha Backend..."
echo "📦 JVM Heap: 256MB - 1024MB"
cd backend
mvn spring-boot:run
