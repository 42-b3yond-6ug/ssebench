# The web UI server tests (bun test), which fake docker and the CLI.
{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../..;
in
pkgs.stdenvNoCC.mkDerivation {
  name = "webui-test";

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference (lib.fileset.unions [
      (root + "/package.json")
      (root + "/webui")
    ]) (root + "/webui/pty-proxy");
  };

  nativeBuildInputs = [ (flake.lib.mkBun pkgs) ];

  configurePhase = ''
    runHook preConfigure
    cp -R ${flake.lib.mkNodeModules pkgs}/. .
    chmod -R u+w node_modules
    runHook postConfigure
  '';

  buildPhase = ''
    runHook preBuild
    export HOME=$TMPDIR
    cd webui
    bun test
    runHook postBuild
  '';

  installPhase = "touch $out";
}
