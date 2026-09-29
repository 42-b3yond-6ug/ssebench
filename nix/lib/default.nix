# Helpers shared by the packages, checks, devshell and formatter.
{ inputs, ... }:
let
  inherit (inputs.nixpkgs) lib;
  root = ../..;
in
rec {
  version = lib.fileContents (root + "/VERSION");

  # The uv workspace; uv.lock is the only place Python dependencies are pinned.
  workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = root; };

  # Python package set for the workspace, built from the locked wheels.
  mkPythonSet =
    pkgs:
    (pkgs.callPackage inputs.pyproject-nix.build.packages { python = pkgs.python312; }).overrideScope (
      lib.composeManyExtensions [
        inputs.pyproject-build-systems.overlays.wheel
        (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
      ]
    );

  # Bun at the version `packageManager` in package.json pins. The hashes must
  # be updated whenever that pin moves.
  mkBun =
    pkgs:
    pkgs.bun.overrideAttrs (
      finalAttrs: prev: {
        version = lib.removePrefix "bun@" (lib.importJSON (root + "/package.json")).packageManager;
        # src follows version through passthru.sources.
        __intentionallyOverridingVersion = true;
        passthru = prev.passthru // {
          sources =
            lib.mapAttrs
              (
                _system:
                { asset, hash }:
                pkgs.fetchurl {
                  url = "https://github.com/oven-sh/bun/releases/download/bun-v${finalAttrs.version}/bun-${asset}.zip";
                  inherit hash;
                }
              )
              {
                x86_64-linux = {
                  asset = "linux-x64-baseline";
                  hash = "sha256-nYokKSpwaAkCBdqsCloiP19pc29Sh+N7+I07QDHtx1A=";
                };
                aarch64-linux = {
                  asset = "linux-aarch64";
                  hash = "sha256-cLrkGzkIsKEg4eWMXIrzDnSvrjuNEbDT/djnh937SyI=";
                };
                aarch64-darwin = {
                  asset = "darwin-aarch64";
                  hash = "sha256-VGfj9l26Umuf6pjwzOBO+vwMY+Fpcz7Ce4dqOtMtoZA=";
                };
              };
        };
      }
    );
}
