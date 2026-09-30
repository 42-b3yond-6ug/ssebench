#!/bin/sh
# Run as root after COPY --chown=1000:1000 has populated SOURCE_DIR.
set -e

SOURCE_DIR="${1:?Usage: setup-source.sh <SOURCE_DIR>}"

# The agent runs as "model" (uid/gid 1000), created fresh: a base image's
# uid-1000 user (ubuntu in ubuntu:24.04) comes with groups such as sudo and adm.
for user in $( (getent passwd 1000 || true; getent passwd model || true) | cut -d: -f1 | sort -u); do
	userdel --remove "$user" 2>/dev/null || userdel "$user"
done
for group in $( (getent group 1000 || true; getent group model || true) | cut -d: -f1 | sort -u); do
	groupdel "$group"
done
groupadd -g 1000 model
useradd -u 1000 -g 1000 -M -d /home/model -s /bin/bash model
mkdir -p /home/model
chown -R model:model /home/model

# The daemon runs the task's build, PoC and test scripts as "sse-runner", a
# system user in a group of its own, so the code the agent writes never runs
# as root or as the agent.
if ! getent passwd sse-runner >/dev/null; then
	useradd --system --user-group --no-create-home --home-dir /nonexistent \
		--shell /usr/sbin/nologin sse-runner
fi
usermod -G "" sse-runner

# Neither user may change what a check uses: toolchains such as the Rust
# image's rustup and cargo directories are world-writable. Sticky temporary
# directories stay as they are.
find / -xdev \( -path /proc -o -path /sys -o -path /dev \) -prune -o \
	-perm -o+w ! -type l ! \( -type d -perm -1000 \) -exec chmod o-w {} +

# Parent of the run's results directory, which the CLI mounts at
# /var/lib/ssebench/results: only root may reach it.
install -d -m 0700 /var/lib/ssebench

find "${SOURCE_DIR}" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true

su model -c "
    git config --global user.name 'SSEBench Agent'
    git config --global user.email 'agent@ssebench.invalid'
    cd '${SOURCE_DIR}'
    git init
    git add -A
    git commit -m 'buggy commit'
"
