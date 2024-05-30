#!/bin/bash
set -e

install_jq() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y jq
        elif command -v yum &> /dev/null; then
            sudo yum install -y epel-release && sudo yum install -y jq
        elif command -v pacman &> /dev/null; then
            sudo pacman -Syu jq
        else
            echo "Unsupported Linux distribution. Please install jq manually."
            return 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install jq
        else
            echo "Homebrew not found. Please install Homebrew and try again."
            return 1
        fi
    elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "Please install jq manually from https://stedolan.github.io/jq/download/"
        return 1
    else
        echo "Unsupported OS. Please install jq manually."
        return 1
    fi
}

install_extensions() {
    if command -v code &> /dev/null; then
        jq -r '.recommendations[]' ./.vscode/extensions.json | xargs -L 1 code --install-extension || {
            echo "Failed to install some extensions with Visual Studio Code."
            return 1
        }
    elif command -v cursor &> /dev/null; then
        jq -r '.recommendations[]' ./.vscode/extensions.json | xargs -L 1 cursor --install-extension || {
            echo "Failed to install some extensions with Cursor."
            return 1
        }
    else
        echo "Neither Visual Studio Code nor Cursor is installed. Please install one of them."
        return 1
    fi
}

install_jq && install_extensions && exit

echo "An error occurred installing extensions for this repo. Please check the output above for details."