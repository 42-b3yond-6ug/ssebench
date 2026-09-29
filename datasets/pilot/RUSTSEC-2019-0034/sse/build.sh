#!/bin/bash -eu
cd /ssebench/harness
RUSTFLAGS="-A deprecated -A warnings" cargo build