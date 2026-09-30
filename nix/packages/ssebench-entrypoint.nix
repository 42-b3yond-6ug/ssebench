{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../../runtime/entrypoint;
in
pkgs.buildGo126Module {
  pname = "ssebench-entrypoint";
  inherit (flake.lib) version;
  # examples/ holds separate modules that build against this one.
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference root (root + "/examples");
  };
  vendorHash = "sha256-SMJbmRGIDk80KyRN+EkFncMBzrrQy1BGpP0UlUfnIag=";

  env.CGO_ENABLED = 0;
  ldflags = [
    "-s"
    "-w"
    "-X main.version=${flake.lib.version}"
  ];

  meta = {
    description = "SSEBench container entrypoint: starts the daemon, the MCP server, the agent and the evaluator";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = lib.licenses.asl20;
    mainProgram = "ssebench-entrypoint";
  };
}
