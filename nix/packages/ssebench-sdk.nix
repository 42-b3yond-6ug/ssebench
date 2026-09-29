# Python environment with the SDK (import name `sse`) and its locked dependencies.
{ pkgs, flake, ... }:
let
  pythonSet = flake.lib.mkPythonSet pkgs;
in
(pythonSet.mkVirtualEnv "ssebench-sdk-env" { ssebench-sdk = [ ]; }).overrideAttrs (old: {
  meta = (old.meta or { }) // {
    description = "SSEBench SDK: Python client for the SSEBench daemon";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = pkgs.lib.licenses.asl20;
  };
})
