#!/bin/bash

# Script to run Glovis filter tests

echo "Setting up test environment..."

# Check if we're in the backend directory
if [ ! -d "venv" ] && [ -d "../venv" ]; then
    cd ..
fi

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Warning: No virtual environment found"
fi

# Install test requirements
echo "Installing test requirements..."
pip install -r tests/requirements.txt

# Run the tests
echo "Running Glovis filter tests..."
echo ""
python tests/test_glovis_filters.py $@

# Exit with the same code as the test script
exit $?