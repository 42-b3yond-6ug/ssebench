package main

// runSidecar runs in sidecar mode: the daemon lives in a separate container,
// so we wait for its socket, then start MCP, run the agent, and evaluate.
func (r *runner) runSidecar() int {
	r.setupSignalHandler()
	defer r.sm.cleanup()

	if err := r.setupArchive(); err != nil {
		logger.Error("Failed to setup archive", "err", err)
		return 1
	}
	r.initLogFiles()

	// The daemon is in the case container; tail its log from the shared volume.
	r.sm.startLogTail(r.logFiles["daemon"])

	logger.Info("Waiting for external daemon socket...")
	if err := waitForSocket(
		r.cfg.daemonSocketPath,
		r.cfg.daemonSocketTimeout,
		"SDK Daemon",
		nil, // no health check — daemon is in another container
		r.cfg.waitLogInterval,
	); err != nil {
		logger.Error("Daemon socket not found", "err", err)
		return 1
	}

	if !r.startMCPServer() {
		return 1
	}

	agentCmd, agentStart, err := r.startAgent()
	if err != nil {
		logger.Error("Failed to start agent", "err", err)
		return 1
	}

	status, elapsed := r.waitAgent(agentCmd, agentStart)
	r.runEvaluator(elapsed)

	return status
}
