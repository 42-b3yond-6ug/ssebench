# Redistributable wheels of the CLI and the SDK, as `uv build` writes them to dist/.
{ pkgs, flake, ... }:
let
  pythonSet = flake.lib.mkPythonSet pkgs;
  dist = name: pythonSet.${name}.override { pyprojectHook = pythonSet.pyprojectDistHook; };
in
pkgs.runCommand "ssebench-wheels-${flake.lib.version}"
  {
    meta = {
      description = "Wheels of the ssebench CLI and the ssebench-sdk Python package";
      homepage = "https://github.com/42-b3yond-6ug/ssebench";
      license = pkgs.lib.licenses.asl20;
    };
  }
  ''
    mkdir -p $out
    cp ${dist "ssebench"}/*.whl ${dist "ssebench-sdk"}/*.whl $out/
  ''
