#!/bin/bash

set -e

echo 'Installing bear...'
apt-get update -qq && apt-get install -y bear

echo 'Parsing config.yaml for source directory...'
if [ -f /ssebench/config.yaml ]; then
  SOURCE_DIR=$(grep '^[[:space:]]*source:' /ssebench/config.yaml | awk '{print $2}' | tr -d '"')
  if [ -n "$SOURCE_DIR" ]; then
    echo "Found source directory: $SOURCE_DIR"
    cd "$SOURCE_DIR"
  else
    echo 'Warning: No source directory found in config.yaml, staying in current directory'
  fi
else
  echo 'Warning: /ssebench/config.yaml not found, staying in current directory'
fi

echo 'Running build with bear...'
if [ -f /ssebench/scripts/build.sh ]; then
  # Check bear version to determine syntax
  BEAR_VERSION=$(bear --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+' | head -n1)
  if [ -n "$BEAR_VERSION" ]; then
    MAJOR_VERSION=$(echo "$BEAR_VERSION" | cut -d. -f1)
    echo "Detected bear version: $BEAR_VERSION"

    # Bear 3.x uses 'bear -- command', Bear 2.x uses 'bear command'
    if [ "$MAJOR_VERSION" -ge 3 ]; then
      echo "Using bear 3.x+ syntax: bear -- command"
      bear -- /ssebench/scripts/build.sh
    else
      echo "Using bear 2.x syntax: bear command"
      bear /ssebench/scripts/build.sh
    fi
  else
    # Fallback: try both syntaxes
    echo "Could not detect bear version, trying both syntaxes..."
    if ! bear -- /ssebench/scripts/build.sh 2>/dev/null; then
      echo "bear -- syntax failed, trying legacy syntax..."
      bear /ssebench/scripts/build.sh
    fi
  fi
else
  echo 'ERROR: /ssebench/scripts/build.sh not found'
  exit 1
fi

echo 'Moving compile_commands.json to /tmp/'
if [ -f compile_commands.json ]; then
  mv compile_commands.json /tmp/compile_commands.json
else
  echo 'ERROR: compile_commands.json was not generated'
  exit 1
fi

echo 'Compilation database generated successfully'

