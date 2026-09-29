import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { loadBindConfig } from "./server/security"

// https://vite.dev/config/
export default defineConfig(({ command }) => {
  const plugins = [react(), tailwindcss()]
  if (command === "build") return { plugins }

  // Same bind rules as the API server: loopback by default, and a token is
  // required before the dev or preview server listens anywhere else.
  const { host } = loadBindConfig()

  // The browser talks to the API on the page's own origin; forward it.
  const apiHost = ["0.0.0.0", "::", "[::]"].includes(host)
    ? "127.0.0.1"
    : host.includes(":") && !host.startsWith("[")
      ? `[${host}]`
      : host
  const proxy = {
    "/api": {
      target: `http://${apiHost}:${process.env.PORT || "3001"}`,
      ws: true,
    },
  }

  return {
    plugins,
    server: { host, port: 5173, proxy },
    preview: { host, proxy },
  }
})
