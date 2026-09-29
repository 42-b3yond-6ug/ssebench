{ pkgs, flake, ... }:
pkgs.buildGo126Module {
  pname = "ssebench-entrypoint";
  inherit (flake.lib) version;
  src = ../../runtime/entrypoint;
  vendorHash = "sha256-2adRLsTSd0vTGcis5FfOT5ZFgB420nvDqHkEEopmgec=";

  env.CGO_ENABLED = 0;
  ldflags = [
    "-s"
    "-w"
    "-X main.version=${flake.lib.version}"
  ];

  meta = {
    description = "SSEBench container entrypoint: starts the daemon, the MCP server, the agent and the evaluator";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
    mainProgram = "ssebench-entrypoint";
  };
}
