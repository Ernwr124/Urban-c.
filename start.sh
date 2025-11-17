#!/bin/bash

echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║            🚀 PROJECT-0 SETUP & START 🚀             ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama is not installed!"
    echo "📥 Please install Ollama from: https://ollama.ai/"
    echo ""
    read -p "Press Enter after installing Ollama..."
fi

# Check if Ollama is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "🔄 Starting Ollama service..."
    ollama serve &
    OLLAMA_PID=$!
    sleep 3
else
    echo "✅ Ollama is already running"
fi

# Check if model is installed
echo "🔍 Checking for GLM-4.6:cloud model..."
if ! ollama list | grep -q "glm-4.6:cloud"; then
    echo "📥 Downloading GLM-4.6:cloud model (this may take a while)..."
    ollama pull glm-4.6:cloud
else
    echo "✅ GLM-4.6:cloud model is ready"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║                                                       ║"
echo "║            ✨ STARTING PROJECT-0 ✨                   ║"
echo "║                                                       ║"
echo "║   Open: http://localhost:8000                        ║"
echo "║                                                       ║"
echo "║   Press Ctrl+C to stop                               ║"
echo "║                                                       ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Start the application
python project0.py

# Cleanup
if [ ! -z "$OLLAMA_PID" ]; then
    kill $OLLAMA_PID
fi
