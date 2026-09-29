package entrypoint

// sandbox runs the full orchestration:
//
//	start daemon → start MCP → (optional) start OpenCode → run agent → evaluate
type sandbox struct{}

func (sandbox) Name() string { return "sandbox" }

func (sandbox) Run(rt *Runtime) int {
	if err := rt.StartDaemon(); err != nil {
		return 1
	}
	if err := rt.StartMCPServer(); err != nil {
		return 1
	}

	rt.StartOpenCodeServer()

	result, err := rt.RunAgent()
	if err != nil {
		logger.Error("Failed to start agent", "err", err)
		return 1
	}

	rt.Evaluate(result)
	rt.KeepAlive()

	return result.ExitStatus
}
