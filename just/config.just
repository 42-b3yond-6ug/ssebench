# Fail fast, propagate errors, catch pipe failures
set shell := ["bash", "-euxo", "pipefail", "-c"]

# Automatically load .env if present
set dotenv-load := true

# Check if main branch has newer commits (warns and prompts y/N)
[no-exit-message]
_check-main-ahead:
    #!/usr/bin/env bash
    set -euo pipefail
    git fetch origin main --quiet 2>/dev/null || true
    
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "")
    
    if [ -z "$REMOTE" ]; then
        echo "Warning: Could not fetch origin/main"
        exit 0
    fi
    
    # Check if origin/main has commits not in current HEAD
    BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "0")
    
    if [ "$BEHIND" -gt 0 ]; then
        echo "Warning: origin/main is $BEHIND commit(s) ahead of current HEAD"
        echo "Consider pulling latest changes before building/pushing."
        echo ""
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborted."
            exit 1
        fi
    fi
