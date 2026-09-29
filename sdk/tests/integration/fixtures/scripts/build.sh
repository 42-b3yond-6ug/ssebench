#!/bin/bash
# Runs in the daemon's copy of the project, as the unprivileged task runner.
set -e

go build ./...
