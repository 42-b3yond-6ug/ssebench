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

  # node_modules of the Bun workspace (webui and docs), fetched from bun.lock,
  # with package bins set to run on Bun instead of `/usr/bin/env node`.
  mkNodeModules =
    pkgs:
    let
      node = pkgs.runCommand "bun-as-node" { } ''
        mkdir -p $out/bin
        ln -s ${lib.getExe (mkBun pkgs)} $out/bin/node
      '';
    in
    pkgs.runCommand "ssebench-node-modules-${version}" { nativeBuildInputs = [ node ]; } ''
      cp -R ${fetchNodeModules pkgs pkgs.stdenv.hostPlatform.system} $out
      chmod -R u+w $out
      patchShebangs $out
    '';

  # The optional native dependencies differ per platform, so each target system
  # has its own hash. Any machine can fetch for any target; after bun.lock
  # changes, refresh each hash from the error of:
  #   nix build --impure --expr 'let f = builtins.getFlake (toString ./.); in
  #     f.lib.fetchNodeModules f.inputs.nixpkgs.legacyPackages.${builtins.currentSystem} "<system>"'
  fetchNodeModules =
    pkgs: target:
    let
      platform = lib.systems.elaborate target;
    in
    pkgs.stdenvNoCC.mkDerivation {
      pname = "ssebench-node-modules-fetched";
      inherit version;

      src = lib.fileset.toSource {
        inherit root;
        fileset = lib.fileset.unions [
          (root + "/package.json")
          (root + "/bun.lock")
          (root + "/bunfig.toml")
          (root + "/webui/package.json")
          (root + "/docs/package.json")
        ];
      };

      nativeBuildInputs = [ (mkBun pkgs) ];

      dontConfigure = true;
      buildPhase = ''
        runHook preBuild
        export HOME=$TMPDIR
        bun install --frozen-lockfile --ignore-scripts --no-progress --backend=copyfile \
          --os=${if platform.isDarwin then "darwin" else "linux"} \
          --cpu=${if platform.isAarch64 then "arm64" else "x64"}
        runHook postBuild
      '';
      installPhase = ''
        runHook preInstall
        mkdir -p $out
        find . -type d -name node_modules -prune -exec cp -R --parents {} $out \;
        runHook postInstall
      '';
      dontFixup = true;

      impureEnvVars = lib.fetchers.proxyImpureEnvVars;
      outputHashMode = "recursive";
      outputHash =
        {
          x86_64-linux = "sha256-eqWHZVAK3L2cFErVamOlwRW3Sua8BpqUVrrG9X+hUi8=";
          aarch64-linux = "sha256-B0dhnNG19+nIreEaQFuavCdvQWgNTu8Dpbz1ceFpmpg=";
          aarch64-darwin = "sha256-z7oSJHvwcmMXYaPGPxOPv155570XCsNCV/5AQ5wx7pw=";
        }
        .${target};
    };

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
