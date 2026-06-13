#!/bin/bash

# setup.sh - Install Python, datasette, and sqlite-utils

set -e  # Exit on error

echo "Starting setup..."

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew is already installed."
fi

# Install Python via Homebrew
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found. Installing Python3..."
    brew install python3
else
    echo "Python3 is already installed: $(python3 --version)"
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install datasette and sqlite-utils
echo "Installing datasette and sqlite-utils..."
pip install datasette sqlite-utils

echo ""
echo "Setup complete!"
echo "To activate the virtual environment, run: source .venv/bin/activate"
echo "To start datasette, run: datasette"
