# The `ssebench` CLI. It finds agents/, images/ and datasets/ in the checkout it
# runs from, or in $SSEBENCH_HOME.
{
  pkgs,
  flake,
  inputs,
  ...
}:
let
  pythonSet = flake.lib.mkPythonSet pkgs;
  inherit (pkgs.callPackages inputs.pyproject-nix.build.util { }) mkApplication;
in
(mkApplication {
  venv = pythonSet.mkVirtualEnv "ssebench-env" { ssebench = [ ]; };
  package = pythonSet.ssebench;
}).overrideAttrs
  (old: {
    meta = (old.meta or { }) // {
      description = "Benchmark AI coding agents on real security vulnerabilities";
      homepage = "https://github.com/42-b3yond-6ug/ssebench";
      license = pkgs.lib.licenses.asl20;
      mainProgram = "ssebench";
    };
  })
