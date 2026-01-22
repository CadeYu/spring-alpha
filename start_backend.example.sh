#!/bin/bash

# Copy this file to start_backend.sh and fill in your API keys
# start_backend.sh is gitignored and won't be committed

export GROQ_API_KEY=your_groq_api_key_here
# export GEMINI_API_KEY=your_gemini_api_key_here

# Increase JVM heap memory (prevents OOM when processing large SEC filings)
export MAVEN_OPTS="-Xms256m -Xmx1024m"

echo "Starting Spring Alpha Backend..."
echo "JVM Heap: 256MB - 1024MB"
cd backend
mvn spring-boot:run
