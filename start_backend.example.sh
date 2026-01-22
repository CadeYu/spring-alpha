#!/bin/bash

# Copy this file to start_backend.sh and fill in your API keys
# start_backend.sh is gitignored and won't be committed

export GROQ_API_KEY=your_groq_api_key_here
# export GEMINI_API_KEY=your_gemini_api_key_here

echo "Starting Spring Alpha Backend..."
cd backend
./mvnw spring-boot:run
