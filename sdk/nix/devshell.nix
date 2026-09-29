{
  pkgs,
  inputs,
  ...
}:
let
  workspace = inputs.uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ../.; };

  overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

  # Editable overlay: sse/ sources resolved at shell-enter time via $REPO_ROOT
  editableOverlay = workspace.mkEditablePyprojectOverlay {
    root = "$REPO_ROOT";
  };

  python = pkgs.python3;
  pythonBase = pkgs.callPackage inputs.pyproject-nix.build.packages { inherit python; };

  pythonSet =
    (pythonBase.overrideScope (
      pkgs.lib.composeManyExtensions [
        inputs.pyproject-build-systems.overlays.default
        overlay
      ]
    )).overrideScope
      editableOverlay;

  # Editable virtualenv: sse/ sources are live via $REPO_ROOT symlink
  virtualenv = pythonSet.mkVirtualEnv "ssebench-dev-env" workspace.deps.all;
in
pkgs.mkShell {
  packages = [
    # Rust toolchain
    pkgs.cargo
    pkgs.rustc
    pkgs.rustfmt
    pkgs.clippy

    # Python toolchain: editable virtualenv + uv for lock management
    virtualenv
    pkgs.uv
    pkgs.ruff
    pkgs.basedpyright

    # Task runner and VCS
    pkgs.just
    pkgs.git
  ];

  env = {
    # Prevent uv from managing its own venv — the Nix editable venv is used
    UV_NO_SYNC = "1";
    # Point uv at the Nix-managed interpreter
    UV_PYTHON = pythonSet.python.interpreter;
    # Prevent uv from downloading Python interpreters
    UV_PYTHON_DOWNLOADS = "never";
  };

  shellHook = ''
    unset PYTHONPATH
    # Required by the editable overlay to resolve sse/ sources at runtime
    export REPO_ROOT=$(git rev-parse --show-toplevel)

    # SSEBench daemon environment
    export SSE_DAEMON_SOCKET=/tmp/ssebench.sock
    export SSE_ARCHIVE=/tmp/sse-archive
    export SSE_HTTP_PORT=4263
    export SSE_BENCH_PATH=/ssebench
  '';
}
