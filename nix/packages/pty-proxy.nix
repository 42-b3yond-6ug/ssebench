{ pkgs, flake, ... }:
pkgs.buildGo126Module {
  pname = "pty-proxy";
  inherit (flake.lib) version;
  src = ../../webui/pty-proxy;
  vendorHash = "sha256-KTzxPnXE4vvPy20h72AayzKM1gHpag5VKtsjiFtB/6o=";

  env.CGO_ENABLED = 0;
  ldflags = [
    "-s"
    "-w"
    "-X main.version=${flake.lib.version}"
  ];

  meta = {
    description = "Gives the SSEBench web UI terminal a real PTY inside a run container";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
    mainProgram = "pty-proxy";
  };
}
