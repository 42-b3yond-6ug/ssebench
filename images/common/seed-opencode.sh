#!/bin/sh
# Run as root after setup-source.sh, with the build's network.
#
# The first request an OpenCode server handles installs its plugin SDK into
# ~/.config/opencode from the npm registry. A run container reaches the LiteLLM
# proxy only, so the image carries that directory, installed here.
set -e

seed=/tmp/opencode-seed
rm -rf "$seed"
mkdir -p "$seed"
cd "$seed"

HOME="$seed" OPENCODE_DISABLE_AUTOUPDATE=1 OPENCODE_DISABLE_MODELS_FETCH=1 \
	opencode serve --port 4199 --hostname 127.0.0.1 >/dev/null 2>&1 &
pid=$!

# package-lock.json is written last. A request can block while the install
# runs, so each one is cut short.
config="$seed/.config/opencode"
for _ in $(seq 120); do
	curl -fs --max-time 5 -X POST -H 'content-type: application/json' -d '{}' \
		http://127.0.0.1:4199/session >/dev/null 2>&1 || true
	[ -f "$config/package-lock.json" ] && break
	sleep 1
done
# The server can outlive SIGTERM while an install is in flight.
kill "$pid" 2>/dev/null || true
for _ in $(seq 10); do
	kill -0 "$pid" 2>/dev/null || break
	sleep 1
done
kill -9 "$pid" 2>/dev/null || true
wait "$pid" 2>/dev/null || true

[ -d "$config/node_modules/@opencode-ai/plugin" ] || {
	echo "OpenCode did not install its plugin SDK" >&2
	exit 1
}
mkdir -p /home/model/.config
mv "$config" /home/model/.config/opencode
chown -R model:model /home/model/.config
rm -rf "$seed"
