#!/bin/bash

set -e  # Exit on any error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Default to release mode
BUILD_MODE="release"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --dev) BUILD_MODE="dev"; shift ;;
        --release) BUILD_MODE="release"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
done

echo -e "${YELLOW}Starting Rust parser build process in ${BUILD_MODE} mode...${NC}"

# Get script directory and ensure we're in the right place
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}"

# Check if we're in the right directory
if [[ ! -f "Cargo.toml" ]]; then
    echo -e "${RED}Error: Must be run from the rust_parser directory${NC}"
    exit 1
fi

# Check for required tools
echo "Checking required tools..."
for cmd in cargo rustc poetry; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}Error: $cmd is required but not installed${NC}"
        exit 1
    fi
done

# Ensure we're in a Poetry environment
if [[ -z "${POETRY_ACTIVE}" ]]; then
    echo -e "${RED}Error: Must be run within a Poetry environment${NC}"
    echo "Please run: poetry shell"
    exit 1
fi

# Ensure maturin is installed in Poetry environment
echo "Ensuring maturin is installed..."
poetry run pip install maturin --quiet || {
    echo -e "${RED}Failed to install maturin${NC}"
    exit 1
}

# Run Rust checks
echo -e "\n${YELLOW}Running Rust checks...${NC}"
echo "Running cargo fmt check..."
cargo fmt -- --check || { echo -e "${RED}Formatting check failed${NC}"; exit 1; }

echo "Running clippy..."
cargo clippy -- -D warnings || { echo -e "${RED}Clippy check failed${NC}"; exit 1; }

# Build with maturin using Poetry's Python
echo -e "\n${YELLOW}Building Rust parser with maturin in ${BUILD_MODE} mode...${NC}"
if [[ "${BUILD_MODE}" == "dev" ]]; then
    poetry run maturin develop || { echo -e "${RED}Maturin development build failed${NC}"; exit 1; }
else
    poetry run maturin develop --release || { echo -e "${RED}Maturin release build failed${NC}"; exit 1; }
fi

# Run basic test to verify the build
echo -e "\n${YELLOW}Running basic verification test...${NC}"
poetry run python -c "from btc_stamps_parser import FastTransactionParser; parser = FastTransactionParser()" || { 
    echo -e "${RED}Verification test failed${NC}"
    exit 1
}

echo -e "${GREEN}✓ Rust parser built and verified successfully in ${BUILD_MODE} mode${NC}" 