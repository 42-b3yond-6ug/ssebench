---
outline: deep
---

# Web UI

SSEBench includes a Web UI for launching runs and watching them live.

## Starting the Web UI

The Web UI requires [Bun](https://bun.sh/). From the repository root:

```bash
cd webui
bun install
bun run prod
```

This builds the frontend and starts the production server. Once started, open your browser to `http://localhost:3001`.

::: info Remote Server Access
If you're running SSEBench on a remote server, you have two options:

1. **Direct access**: Navigate to `http://<your-server-ip>:3001`. Make sure port 3001 is open in your server's firewall.

2. **SSH tunnel (recommended)**: Forward the port through SSH for secure access without opening firewall ports:
   ```bash
   ssh -L 3001:localhost:3001 user@your-server
   ```
   Then access the Web UI at `http://localhost:3001` from your local machine.
:::

## Features

The Web UI provides:
- **Task Browser**: Browse and select benchmark tasks
- **Launch Wizard**: Configure and launch benchmarks interactively
- **Live Logs**: Stream launch output in real-time
- **Container Management**: Attach to running containers, view terminal output
- **AI Session Viewer**: Monitor agent conversations and tool executions

::: tip
Make sure the LiteLLM proxy is running (`just launch`) before launching tasks from the Web UI.
:::
