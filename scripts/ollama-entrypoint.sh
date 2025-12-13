#!/bin/bash
set -e

echo "Starting Ollama service with GPU monitoring..."

# Start GPU monitoring in background (logs every 30 seconds)
nvidia-smi dmon -s pucvmet -d 30 &

# Start Ollama server in background
echo "Starting Ollama server..."
ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama service to be ready..."
for i in {1..36}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama service is ready"
        break
    fi
    sleep 5
done

# Check if service started successfully
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Failed to start Ollama service"
    exit 1
fi

# Pull the model (may take 2-5 minutes on first run)
echo "Pulling model (may take 2-5 minutes on first run)..."
if ! ollama pull hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF; then
    echo "ERROR: Failed to pull model - check network and disk space"
    exit 1
fi

# Warm the model by running a test inference
echo "Warming model..."
if ! curl -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF","prompt":"Test","stream":false}' \
    > /dev/null 2>&1; then
    echo "ERROR: Failed to warm model"
    exit 1
fi

echo "Ollama ready with model loaded"

# Keep container running
wait
