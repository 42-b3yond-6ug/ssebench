# The web UI: the built client, the API server bundled into one file, and the
# pty-proxy helper at the path the server looks for it.
{
  pkgs,
  flake,
  perSystem,
  ...
}:
let
  inherit (pkgs) lib;
  root = ../..;
  bun = flake.lib.mkBun pkgs;
  nodeModules = flake.lib.mkNodeModules pkgs;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "ssebench-webui";
  inherit (flake.lib) version;

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.difference (lib.fileset.unions [
      (root + "/package.json")
      (root + "/webui")
    ]) (root + "/webui/pty-proxy");
  };

  nativeBuildInputs = [
    bun
    pkgs.makeWrapper
  ];

  configurePhase = ''
    runHook preConfigure
    cp -R ${nodeModules}/. .
    chmod -R u+w node_modules
    runHook postConfigure
  '';

  buildPhase = ''
    runHook preBuild
    export HOME=$TMPDIR
    bun run --cwd webui build
    bun build webui/server/index.ts --target=bun --outfile=webui/server-bundle/index.js
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    share=$out/share/ssebench-webui
    mkdir -p $share/pty-proxy
    cp -R webui/dist $share/dist
    cp -R webui/server-bundle $share/server
    ln -s ${lib.getExe perSystem.self.pty-proxy} $share/pty-proxy/pty-proxy
    # The server serves ./dist, and runs the CLI in SSEBENCH_PATH, which
    # defaults to the directory it was started from.
    makeWrapper ${lib.getExe bun} $out/bin/ssebench-webui \
      --run 'export SSEBENCH_PATH="''${SSEBENCH_PATH:-$PWD}"' \
      --chdir $share \
      --add-flags $share/server/index.js
    runHook postInstall
  '';

  meta = {
    description = "SSEBench web UI: launch runs and watch them live";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = lib.licenses.asl20;
    mainProgram = "ssebench-webui";
  };
}
