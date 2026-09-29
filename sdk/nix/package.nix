# Default package: bundles ssebench-daemon + ssebench-sdk into one derivation.
# `nix build` installs both the daemon binary and the Python library.
{ pkgs, perSystem, ... }:
pkgs.symlinkJoin {
  name = "ssebench";
  paths = [
    perSystem.self.ssebench-daemon
    perSystem.self.ssebench-sdk
  ];

  meta = {
    description = "SSEBench SDK – daemon binary and Python client library";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
  };
}
