# ssebench-sdk: Python virtualenv built from uv.lock via uv2nix.
# Dependencies are resolved entirely from uv.lock — no manual listing in Nix.
{ pkgs, inputs, ... }:
let
  workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ../../../.; };

  overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

  python = pkgs.python3;
  pythonBase = pkgs.callPackage inputs.pyproject-nix.build.packages { inherit python; };

  pythonSet = pythonBase.overrideScope (
    pkgs.lib.composeManyExtensions [
      inputs.pyproject-build-systems.overlays.default
      overlay
    ]
  );
in
pythonSet.mkVirtualEnv "ssebench-sdk-env" workspace.deps.default
