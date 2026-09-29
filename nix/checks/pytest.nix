{ pkgs, flake, ... }:
let
  venv = (flake.lib.mkPythonSet pkgs).mkVirtualEnv "ssebench-dev-env" flake.lib.pythonDeps;
in
pkgs.runCommand "pytest" { nativeBuildInputs = [ venv ]; } ''
  cp -R ${flake} src
  chmod -R u+w src
  cd src
  # Import the CLI and the SDK from this tree, as the editable installs of
  # `uv sync` do; the CLI locates the checkout from its own path.
  export PYTHONPATH=$PWD/bench/src:$PWD/sdk/python
  export HOME=$TMPDIR
  pytest -p no:cacheprovider
  touch $out
''
