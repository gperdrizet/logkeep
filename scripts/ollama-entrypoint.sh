#!/bin/bash
set -e

echo "Starting Ollama service with GPU monitoring..."

# Start GPU monitoring in background (logs every 30 seconds)
nvidia-smi dmon -s pucvmet -d 30 &

# Start Ollama server in background
echo "Starting Ollama server..."
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

# Give it a moment to start
sleep 3

# Wait for Ollama to be ready
echo "Waiting for Ollama service to be ready..."
READY=0
for i in {1..60}; do
    echo "Attempt $i/60..."
    if ollama list > /dev/null 2>&1; then
        echo "Ollama service is ready"
        READY=1
        break
    fi
    sleep 5
done

# Check if service started successfully
if [ $READY -eq 0 ]; then
    echo "ERROR: Failed to start Ollama service after 300 seconds"
    echo "Last 20 lines of ollama.log:"
    tail -20 /tmp/ollama.log
    exit 1
fi

# Pull the model (may take 2-5 minutes on first run)
echo "Pulling model (may take 2-5 minutes on first run)..."
if ! ollama pull hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF; then
    echo "ERROR: Failed to pull model - check network and disk space"
    exit 1
fi

# Warm the model by running a test inference (optional, don't fail if it doesn't work)
echo "Warming model..."
if curl -X POST http://localhost:11434/api/generate \
    -H "Content-Type: application/json" \
    -d '{"model":"hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF","prompt":"Test","stream":false}' \
    > /dev/null 2>&1; then
    echo "Model warmed successfully"
else
    echo "Warning: Failed to warm model (will warm on first use)"
fi

echo "Ollama ready with model loaded"

# Keep container running and show ollama output
tail -f /tmp/ollama.log
