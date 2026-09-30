#!/bin/sh
# Let every user read the toolchains and dependency caches that the image build
# installed as root.
#
# The runner builds and tests as another user than root, in a copy of the
# project, so it can only use what others may read. Archives keep their own
# modes when they are unpacked, and some crates ship files as 0640; without this
# the runner fails to compile them. Only read access is added.
set -e

for dir in "${CARGO_HOME:-}" "${RUSTUP_HOME:-}" "${GOPATH:-}"; do
	[ -d "$dir" ] || continue
	find "$dir" -type f ! -perm -o+r -exec chmod o+r {} +
	find "$dir" -type d ! -perm -o+rx -exec chmod o+rx {} +
done
