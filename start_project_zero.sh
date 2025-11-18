#!/bin/bash

echo "🚀 Starting Project-0 Production SaaS..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip is not installed. Please install pip first."
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements_project_zero.txt

echo ""
echo "✅ Dependencies installed!"
echo ""

# Check if Ollama is running
echo "🔍 Checking Ollama..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running!"
else
    echo "⚠️  Ollama is not running. Please start Ollama first:"
    echo "   ollama serve"
    echo ""
    echo "   Then run: ollama pull glm-4.6:cloud"
    echo ""
fi

echo ""
echo "🎯 Starting Project-0..."
echo "📍 Landing Page: http://localhost:8000"
echo "🔐 Authentication: Enabled"
echo "💾 Database: project_zero.db"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 project_zero.py
