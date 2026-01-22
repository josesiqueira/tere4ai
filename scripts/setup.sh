#!/bin/bash
# TERE4AI Setup Script
# Automated setup for local development

set -e

echo "========================================"
echo "  TERE4AI - Setup Script"
echo "  Trustworthy Ethical Requirements"
echo "  Engineering for AI"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from project root
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Run this script from the project root directory${NC}"
    echo "  cd /path/to/tere4ai && ./scripts/setup.sh"
    exit 1
fi

# Step 1: Check Python version
echo -e "${YELLOW}[1/6] Checking Python version...${NC}"
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Python not found. Please install Python 3.10+${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Found Python $PYTHON_VERSION"

# Step 2: Create virtual environment
echo -e "${YELLOW}[2/6] Creating virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo "  .venv already exists, skipping..."
else
    $PYTHON_CMD -m venv .venv
    echo "  Created .venv"
fi

# Step 3: Activate and install dependencies
echo -e "${YELLOW}[3/6] Installing dependencies...${NC}"
source .venv/bin/activate
pip install --upgrade pip -q
pip install -e . -q
echo "  Dependencies installed"

# Step 4: Check for .env file
echo -e "${YELLOW}[4/6] Checking configuration...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${YELLOW}Created .env from .env.example${NC}"
        echo -e "  ${RED}IMPORTANT: Edit .env and add your OPENAI_API_KEY${NC}"
    else
        echo -e "  ${RED}Warning: No .env file found${NC}"
    fi
else
    echo "  .env file exists"
fi

# Step 5: Check Docker
echo -e "${YELLOW}[5/6] Checking Docker...${NC}"
if command -v docker &> /dev/null; then
    echo "  Docker is installed"
    if docker info &> /dev/null; then
        echo "  Docker daemon is running"
    else
        echo -e "  ${YELLOW}Docker daemon not running. Start it to use docker-compose${NC}"
    fi
else
    echo -e "  ${YELLOW}Docker not found. Install Docker for easy Neo4j setup${NC}"
fi

# Step 6: Summary
echo ""
echo -e "${GREEN}========================================"
echo "  Setup Complete!"
echo "========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit .env and add your OPENAI_API_KEY"
echo "     nano .env"
echo ""
echo "  2. Start Neo4j and the API:"
echo "     docker-compose up -d"
echo ""
echo "  3. Run data ingestion (first time only):"
echo "     docker-compose --profile ingestion up"
echo ""
echo "  4. Open the web interface:"
echo "     http://localhost:8000"
echo ""
echo "For manual setup (without Docker):"
echo "  source .venv/bin/activate"
echo "  # Start your own Neo4j instance"
echo "  # Run: python -m ingestion.scripts.ingest_all"
echo "  # Run: uvicorn api.main:app --reload"
echo ""
