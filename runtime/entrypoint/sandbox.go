package main

// runSandbox runs the full orchestration mode:
//
//	start daemon → start MCP → (optional) start OpenCode → run agent → evaluate
func (r *runner) runSandbox() int {
	r.setupSignalHandler()

	defer func() {
		if !r.cfg.keepAlive {
			r.sm.cleanup()
		}
	}()

	if err := r.setupArchive(); err != nil {
		logger.Error("Failed to setup archive", "err", err)
		return 1
	}
	r.initLogFiles()

	if !r.startDaemon() {
		return 1
	}
	if !r.startMCPServer() {
		return 1
	}

	r.startOpenCodeServer()

	agentCmd, agentStart, err := r.startAgent()
	if err != nil {
		logger.Error("Failed to start agent", "err", err)
		return 1
	}

	status, elapsed := r.waitAgent(agentCmd, agentStart)
	r.notifyAgentExited()
	r.runEvaluator(elapsed)
	r.handleKeepAlive()

	return status
}
