#!/usr/bin/env bash
# Script to run tests with various options

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Pipeline Scripts Test Runner${NC}"
echo "=============================="
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}ERROR: pytest is not installed${NC}"
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

# Parse arguments
TEST_TYPE="${1:-all}"
COVERAGE="${2:-no}"

case "$TEST_TYPE" in
    all)
        echo -e "${YELLOW}Running all tests...${NC}"
        if [ "$COVERAGE" = "coverage" ]; then
            pytest tests/ -v --cov=scripts --cov-report=term-missing --cov-report=html
            echo -e "${GREEN}Coverage report generated in htmlcov/index.html${NC}"
        else
            pytest tests/ -v
        fi
        ;;

    unit)
        echo -e "${YELLOW}Running unit tests only...${NC}"
        pytest tests/ -m unit -v
        ;;

    integration)
        echo -e "${YELLOW}Running integration tests only...${NC}"
        pytest tests/ -m integration -v
        ;;

    fast)
        echo -e "${YELLOW}Running fast tests (excluding slow tests)...${NC}"
        pytest tests/ -m "not slow" -v
        ;;

    file)
        if [ -z "$2" ]; then
            echo -e "${RED}ERROR: Please specify a test file${NC}"
            echo "Usage: $0 file test_nanopore_metadata.py"
            exit 1
        fi
        TEST_FILE="$2"
        echo -e "${YELLOW}Running tests from $TEST_FILE...${NC}"
        pytest "tests/$TEST_FILE" -v
        ;;

    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo ""
        echo "Usage: $0 [test_type] [coverage]"
        echo ""
        echo "Test types:"
        echo "  all         - Run all tests (default)"
        echo "  unit        - Run only unit tests"
        echo "  integration - Run only integration tests"
        echo "  fast        - Run all tests except slow ones"
        echo "  file <name> - Run specific test file"
        echo ""
        echo "Coverage:"
        echo "  coverage    - Generate coverage report (only with 'all')"
        echo ""
        echo "Examples:"
        echo "  $0                                    # Run all tests"
        echo "  $0 all coverage                       # Run all tests with coverage"
        echo "  $0 unit                               # Run unit tests only"
        echo "  $0 file test_nanopore_metadata.py     # Run specific file"
        exit 1
        ;;
esac

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}✗ Some tests failed${NC}"
    exit 1
fi

