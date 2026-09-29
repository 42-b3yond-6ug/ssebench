/**
 * ExecutionModeDiagram - Detailed SVG architecture diagrams
 *
 * Visual representations of Sandbox vs Sidecar execution modes.
 */

interface DiagramProps {
  mode: "sandbox" | "sidecar"
}

export function ExecutionModeDiagram({ mode }: DiagramProps) {
  if (mode === "sandbox") {
    return <SandboxDiagram />
  }
  return <SidecarDiagram />
}

function SandboxDiagram() {
  return (
    <svg
      viewBox="0 0 300 200"
      className="h-full w-full"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer container */}
      <rect
        x="40"
        y="20"
        width="220"
        height="160"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="6,4"
        className="text-fg-3"
      />
      <text
        x="150"
        y="15"
        textAnchor="middle"
        className="fill-fg-4 text-xs"
        style={{ fontSize: "10px" }}
      >
        Container: ssebench-task
      </text>

      {/* Agent process box */}
      <rect
        x="70"
        y="50"
        width="160"
        height="50"
        rx="4"
        className="fill-gruvbox-aqua/10 stroke-gruvbox-aqua"
        strokeWidth="2"
      />
      <text
        x="150"
        y="72"
        textAnchor="middle"
        className="fill-gruvbox-aqua font-medium"
        style={{ fontSize: "12px" }}
      >
        Agent Process
      </text>
      <text
        x="150"
        y="88"
        textAnchor="middle"
        className="fill-fg-4"
        style={{ fontSize: "9px" }}
      >
        (claude-code/codex)
      </text>

      {/* Bidirectional arrow */}
      <path
        d="M 150 105 L 150 120"
        className="stroke-gruvbox-orange"
        strokeWidth="2"
        markerEnd="url(#arrowdown)"
      />
      <path
        d="M 150 145 L 150 130"
        className="stroke-gruvbox-orange"
        strokeWidth="2"
        markerEnd="url(#arrowup)"
      />
      <text
        x="165"
        y="127"
        className="fill-gruvbox-orange"
        style={{ fontSize: "10px" }}
      >
        IPC
      </text>

      {/* SDK server box */}
      <rect
        x="70"
        y="130"
        width="160"
        height="40"
        rx="4"
        className="fill-gruvbox-green/10 stroke-gruvbox-green"
        strokeWidth="2"
      />
      <text
        x="150"
        y="150"
        textAnchor="middle"
        className="fill-gruvbox-green font-medium"
        style={{ fontSize: "12px" }}
      >
        SDK Server
      </text>
      <text
        x="150"
        y="162"
        textAnchor="middle"
        className="fill-fg-4"
        style={{ fontSize: "9px" }}
      >
        (HTTP API)
      </text>

      {/* Arrow markers */}
      <defs>
        <marker
          id="arrowdown"
          markerWidth="10"
          markerHeight="10"
          refX="5"
          refY="5"
          orient="auto"
        >
          <polygon points="0,0 10,5 0,10" className="fill-gruvbox-orange" />
        </marker>
        <marker
          id="arrowup"
          markerWidth="10"
          markerHeight="10"
          refX="5"
          refY="5"
          orient="auto"
        >
          <polygon points="0,0 10,5 0,10" className="fill-gruvbox-orange" />
        </marker>
      </defs>
    </svg>
  )
}

function SidecarDiagram() {
  return (
    <svg
      viewBox="0 0 340 200"
      className="h-full w-full"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Agent container */}
      <rect
        x="20"
        y="40"
        width="130"
        height="120"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="6,4"
        className="text-fg-3"
      />
      <text
        x="85"
        y="35"
        textAnchor="middle"
        className="fill-fg-4 text-xs"
        style={{ fontSize: "10px" }}
      >
        agent-container
      </text>

      {/* Agent process box */}
      <rect
        x="35"
        y="70"
        width="100"
        height="70"
        rx="4"
        className="fill-gruvbox-aqua/10 stroke-gruvbox-aqua"
        strokeWidth="2"
      />
      <text
        x="85"
        y="100"
        textAnchor="middle"
        className="fill-gruvbox-aqua font-medium"
        style={{ fontSize: "12px" }}
      >
        Agent
      </text>
      <text
        x="85"
        y="115"
        textAnchor="middle"
        className="fill-fg-4"
        style={{ fontSize: "9px" }}
      >
        Process
      </text>

      {/* SDK container */}
      <rect
        x="190"
        y="40"
        width="130"
        height="120"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="6,4"
        className="text-fg-3"
      />
      <text
        x="255"
        y="35"
        textAnchor="middle"
        className="fill-fg-4 text-xs"
        style={{ fontSize: "10px" }}
      >
        sdk-container
      </text>

      {/* SDK server box */}
      <rect
        x="205"
        y="70"
        width="100"
        height="70"
        rx="4"
        className="fill-gruvbox-green/10 stroke-gruvbox-green"
        strokeWidth="2"
      />
      <text
        x="255"
        y="100"
        textAnchor="middle"
        className="fill-gruvbox-green font-medium"
        style={{ fontSize: "12px" }}
      >
        SDK
      </text>
      <text
        x="255"
        y="115"
        textAnchor="middle"
        className="fill-fg-4"
        style={{ fontSize: "9px" }}
      >
        Server
      </text>

      {/* Bidirectional arrow between containers */}
      <path
        d="M 140 105 L 185 105"
        className="stroke-gruvbox-orange"
        strokeWidth="2"
        markerEnd="url(#arrowright-sidecar)"
      />
      <path
        d="M 200 105 L 155 105"
        className="stroke-gruvbox-orange"
        strokeWidth="2"
        markerEnd="url(#arrowleft-sidecar)"
      />
      <text
        x="170"
        y="95"
        textAnchor="middle"
        className="fill-gruvbox-orange"
        style={{ fontSize: "10px" }}
      >
        HTTP
      </text>

      {/* Network label */}
      <text
        x="170"
        y="180"
        textAnchor="middle"
        className="fill-fg-4"
        style={{ fontSize: "10px" }}
      >
        Docker Network
      </text>

      {/* Arrow markers */}
      <defs>
        <marker
          id="arrowright-sidecar"
          markerWidth="10"
          markerHeight="10"
          refX="5"
          refY="5"
          orient="auto"
        >
          <polygon points="0,0 10,5 0,10" className="fill-gruvbox-orange" />
        </marker>
        <marker
          id="arrowleft-sidecar"
          markerWidth="10"
          markerHeight="10"
          refX="5"
          refY="5"
          orient="auto"
        >
          <polygon points="0,0 10,5 0,10" className="fill-gruvbox-orange" />
        </marker>
      </defs>
    </svg>
  )
}
