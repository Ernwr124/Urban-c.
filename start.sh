#!/bin/bash

# HR Platform Startup Script

echo "🚀 Starting HR Platform..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create uploads directory
mkdir -p uploads

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "⚙️  Please edit .env file with your configuration"
fi

# Start the application
echo "✅ Starting HR Platform on http://localhost:8000"
python hr_platform.py
