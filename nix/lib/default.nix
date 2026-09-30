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

  # Every member with its dependency groups, plus the root `dev` group (ruff,
  # basedpyright, pytest), which uv2nix does not resolve on its own.
  pythonDeps =
    let
      devGroup = (lib.importTOML (root + "/pyproject.toml")).dependency-groups.dev;
      name = spec: (inputs.pyproject-nix.lib.pep508.parseString spec).name;
    in
    workspace.deps.all // lib.genAttrs (map name devGroup) (_: [ ]);

  # Python package set for the workspace, built from the locked wheels.
  mkPythonSet =
    pkgs:
    (pkgs.callPackage inputs.pyproject-nix.build.packages { python = pkgs.python312; }).overrideScope (
      lib.composeManyExtensions [
        inputs.pyproject-build-systems.overlays.wheel
        (workspace.mkPyprojectOverlay {
          sourcePreference = "wheel";
          dependencies = pythonDeps;
        })
      ]
    );

  # `nix fmt` and the formatting check. The web UI keeps its own Prettier setup
  # (`bun run --cwd webui format`): its Tailwind plugin sorts classes by the
  # tailwindcss it finds in the workspace node_modules.
  mkTreefmt =
    pkgs:
    inputs.treefmt-nix.lib.evalModule pkgs {
      projectRootFile = "flake.nix";
      # Task sources are upstream code and keep their own style.
      settings.global.excludes = [ "datasets/**" ];

      programs.nixfmt.enable = true;
      programs.ruff-format = {
        enable = true;
        package = lib.addMetaAttrs { mainProgram = "ruff"; } (mkPythonSet pkgs).ruff;
      };
      # Apply extend-exclude from pyproject.toml to the paths treefmt passes.
      settings.formatter.ruff-format.options = [ "--force-exclude" ];
      programs.rustfmt = {
        enable = true;
        # cargo fmt passes the crates' edition; rustfmt.toml sets the style.
        edition = (lib.importTOML (root + "/Cargo.toml")).workspace.package.edition;
      };
      programs.gofmt = {
        enable = true;
        package = pkgs.go_1_26;
      };
    };

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
          x86_64-linux = "sha256-YOVXPj59kak9RSvYZxTOkE9gZZoG6nYpUFUMmxcEgIg=";
          aarch64-linux = "sha256-axV7hpOYJtHHUBUIRSyQpmCrXdYxVYjHjATrA6ZTz7g=";
          aarch64-darwin = "sha256-QCZbHsrMEngL5YxDaRaJr7IdhXmEerOKUzHNIc4Bzzw=";
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
                  hash = "sha256-xngEDxT+BEDrg503y9DOTAUaMtpygGrJfeamqra/co8=";
                };
                aarch64-linux = {
                  asset = "linux-aarch64";
                  hash = "sha256-VDKLvC2cjgyfiSxUTWbFeoO4QTnjSQnl7oF1jxrI/ac=";
                };
                aarch64-darwin = {
                  asset = "darwin-aarch64";
                  hash = "sha256-kJh6OhbX21VtiGrD1VHnttPt8KHPQ6yu1iLoZ2vh0S8=";
                };
              };
        };
      }
    );
}
