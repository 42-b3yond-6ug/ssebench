#!/bin/sh
# Run as root after COPY --chown=1000:1000 has populated SOURCE_DIR.
set -e

SOURCE_DIR="${1:?Usage: setup-source.sh <SOURCE_DIR>}"

# Create "model" user at uid/gid 1000, renaming any existing uid-1000 user
if getent passwd 1000 >/dev/null; then
	existing_user=$(getent passwd 1000 | cut -d: -f1)
	if [ "$existing_user" != "model" ]; then
		usermod -l model "$existing_user"
		groupmod -n model "$(getent group 1000 | cut -d: -f1)"
	fi
else
	groupadd -g 1000 model
	useradd -m -u 1000 -g 1000 -s /bin/bash model
fi
mkdir -p /home/model
chown -R model:model /home/model

find "${SOURCE_DIR}" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

su model -c "
    git config --global user.name 'SSEBench'
    git config --global user.email 'bench@ssebench.local'
    cd '${SOURCE_DIR}'
    git init
    git add -A
    git commit -m 'buggy commit'
"

git config --global --add safe.directory "${SOURCE_DIR}"
