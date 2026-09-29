# ssebench-wheel: builds the distributable Python wheel (`.whl`) for ssebench.sdk.
#
# Unlike ssebench-sdk (which produces a runnable virtualenv via uv2nix), this
# derivation produces the publishable wheel artifact consumed by downstream
# package indexes such as PyPI.
{ pkgs, flake, ... }:
let
  # Pure-Python wheel: setuptools backend, no native extensions, so a plain
  # `pip wheel --no-deps` call inside the sandbox is sufficient and hermetic.
  python = pkgs.python3;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "ssebench-sdk-wheel";
  version = (pkgs.lib.importTOML "${flake}/pyproject.toml").project.version;

  src = flake;

  nativeBuildInputs = [
    python
    python.pkgs.pip
    python.pkgs.wheel
    python.pkgs.setuptools
  ];

  dontConfigure = true;

  buildPhase = ''
    runHook preBuild
    export HOME=$TMPDIR
    python -m pip wheel . --no-deps --no-build-isolation -w dist
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p $out
    cp dist/*.whl $out/
    runHook postInstall
  '';

  meta = {
    description = "Distributable Python wheel for the SSEBench SDK";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
  };
}
