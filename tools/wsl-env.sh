#!/bin/bash
# Helper script for using the WSL environment

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}SocketCAN-SA WSL Environment${NC}"
echo "=================================="

# Navigate to project directory
PROJECT_DIR="/mnt/d/workspace/GitHub/socketcan-sa"
cd "$PROJECT_DIR" || exit 1

# Activate virtual environment
echo -e "${GREEN}Activating WSL Python 3.12.3 virtual environment...${NC}"
source .venv-wsl/bin/activate

# Show Python version
echo -e "${GREEN}Python version:${NC} $(python --version)"
echo -e "${GREEN}Virtual environment:${NC} $VIRTUAL_ENV"

# Add src to Python path for this session
export PYTHONPATH="$PROJECT_DIR/src:$PYTHONPATH"

echo ""
echo -e "${GREEN}Ready!${NC} You can now run:"
echo "  python -m pytest tests/         # Run tests"
echo "  python -c 'from socketcan_sa.shaper import run_bridge'  # Test imports"
echo "  python src/socketcan_sa/shaper.py --help    # Run shaper"
echo ""

# Start interactive shell
exec bash