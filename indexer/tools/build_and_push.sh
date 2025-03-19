#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get version from VERSION file if it exists
if [ -f "$(dirname "$0")/../../VERSION" ]; then
    VERSION_TAG=$(cat "$(dirname "$0")/../../VERSION")
    # Sanitize version for Docker tag (replace + with - since + is not allowed in Docker tags)
    DOCKER_TAG=$(echo "${VERSION_TAG}" | sed 's/+/-/g')
else
    VERSION_TAG="latest"
    DOCKER_TAG="${VERSION_TAG}"
fi

# Default values
TAG="${DOCKER_TAG}"
PUSH=false
SCAN=false
DOCKER_HUB_USER="btcstamps"
REPO_NAME="indexer"

# Load environment variables from .env file if it exists
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Loading environment variables from .env file...${NC}"
    # Export variables from .env file
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Process command line arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --tag) 
            # Sanitize provided tag as well
            TAG=$(echo "$2" | sed 's/+/-/g')
            shift 
            ;;
        --push) PUSH=true ;;
        --scan) SCAN=true ;;
        --help) 
            echo "Usage: $0 [OPTIONS]"
            echo "Build and optionally push Docker image for BTC Stamps Indexer"
            echo ""
            echo "Options:"
            echo "  --tag TAG     Specify image tag (default: ${VERSION_TAG}, sanitized as ${DOCKER_TAG})"
            echo "  --push        Push to DockerHub after building"
            echo "  --scan        Run Trivy vulnerability scanner on the image (similar to CI)"
            echo "  --help        Show this help message"
            exit 0
            ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Ensure we're in the correct directory
cd "$(dirname "$0")/.." || exit 1
INDEXER_DIR="$(pwd)"

echo -e "${YELLOW}Building Docker image for BTC Stamps Indexer...${NC}"
echo "Version: ${VERSION_TAG}"
echo "Docker Tag: ${TAG}"
echo "Push: ${PUSH}"
echo "Scan: ${SCAN}"

# Build the Docker image
echo -e "\n${YELLOW}Building Docker image...${NC}"
if docker build -t "${DOCKER_HUB_USER}/${REPO_NAME}:${TAG}" .; then
    echo -e "${GREEN}✅ Build successful${NC}"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Run a simple test to verify the build
echo -e "\n${YELLOW}Testing Docker image...${NC}"
if docker run --rm "${DOCKER_HUB_USER}/${REPO_NAME}:${TAG}" poetry run python -c "from btc_stamps_parser import FastTransactionParser; print('Rust parser loaded successfully')"; then
    echo -e "${GREEN}✅ Test passed${NC}"
else
    echo -e "${RED}❌ Test failed${NC}"
    exit 1
fi

# Push to DockerHub if requested
if [ "$PUSH" = true ]; then
    echo -e "\n${YELLOW}Pushing to DockerHub...${NC}"
    
    # Check for DockerHub credentials
    if [ -z "$DOCKERHUB_TOKEN" ]; then
        echo -e "${YELLOW}DOCKERHUB_TOKEN environment variable not set.${NC}"
        echo -e "Please login to DockerHub manually with:"
        echo -e "docker login -u ${DOCKER_HUB_USER}"
        
        # Try to login interactively
        if docker login -u "${DOCKER_HUB_USER}"; then
            echo -e "${GREEN}Login successful${NC}"
        else
            echo -e "${RED}Login failed${NC}"
            exit 1
        fi
    else
        # Login with environment variable
        echo -e "Logging in to DockerHub using token..."
        echo "$DOCKERHUB_TOKEN" | docker login -u "${DOCKER_HUB_USER}" --password-stdin
    fi
    
    # Push the image
    if docker push "${DOCKER_HUB_USER}/${REPO_NAME}:${TAG}"; then
        echo -e "${GREEN}✅ Successfully pushed to DockerHub${NC}"
    else
        echo -e "${RED}❌ Failed to push to DockerHub${NC}"
        exit 1
    fi
fi

# Run vulnerability scan if requested
if [ "$SCAN" = true ]; then
    echo -e "\n${YELLOW}Running Trivy vulnerability scanner...${NC}"
    
    # Check if Trivy is installed
    if ! command -v trivy &> /dev/null; then
        echo -e "${YELLOW}Trivy not found, attempting to install...${NC}"
        
        # Try to install Trivy using package manager
        if command -v apt-get &> /dev/null; then
            echo "Detected apt package manager"
            echo "Installing Trivy via Aqua Security's repository..."
            sudo apt-get install -y wget apt-transport-https gnupg lsb-release
            wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
            echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee -a /etc/apt/sources.list.d/trivy.list
            sudo apt-get update
            sudo apt-get install -y trivy
        else
            echo -e "${RED}Cannot install Trivy automatically.${NC}"
            echo "Please install Trivy manually: https://aquasecurity.github.io/trivy/latest/getting-started/installation/"
            exit 1
        fi
    fi
    
    # Files to skip during scan (large files)
    SKIP_FILES="app/bootstrap/srcbackground.csv,/usr/src/app/files/**"
    
    # Run Trivy scan with CI-like settings, skipping large files
    echo -e "\n${YELLOW}Running scan (skipping large files)...${NC}"
    if trivy image --format table --exit-code 0 --severity HIGH,CRITICAL --skip-files "${SKIP_FILES}" "${DOCKER_HUB_USER}/${REPO_NAME}:${TAG}"; then
        echo -e "${GREEN}✅ Vulnerability scan complete${NC}"
        
        # Also run with exit-code 1 to show what would happen in CI for CRITICAL vulns
        echo -e "\n${YELLOW}Checking for CRITICAL vulnerabilities (would fail CI)...${NC}"
        if trivy image --format table --exit-code 1 --severity CRITICAL --skip-files "${SKIP_FILES}" "${DOCKER_HUB_USER}/${REPO_NAME}:${TAG}"; then
            echo -e "${GREEN}✅ No CRITICAL vulnerabilities detected${NC}"
        else
            echo -e "${RED}⚠️ CRITICAL vulnerabilities detected - would fail CI${NC}"
        fi
    else
        echo -e "${RED}❌ Vulnerability scan failed${NC}"
    fi
fi

echo -e "\n${GREEN}Process completed successfully${NC}" 