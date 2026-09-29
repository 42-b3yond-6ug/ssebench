# The documentation site, built to static files.
{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../..;
  nodeModules = flake.lib.mkNodeModules pkgs;
in
pkgs.stdenvNoCC.mkDerivation {
  pname = "ssebench-docs";
  inherit (flake.lib) version;

  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/package.json")
      (root + "/VERSION")
      (root + "/docs")
    ];
  };

  nativeBuildInputs = [ (flake.lib.mkBun pkgs) ];

  configurePhase = ''
    runHook preConfigure
    cp -R ${nodeModules}/. .
    chmod -R u+w node_modules
    runHook postConfigure
  '';

  # The build log is a zero-width terminal, on which VitePress's progress
  # spinner redraws forever; CI turns the spinner off.
  env.CI = "1";

  buildPhase = ''
    runHook preBuild
    export HOME=$TMPDIR
    bun run --cwd docs build
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    cp -R docs/.vitepress/dist $out
    runHook postInstall
  '';

  meta = {
    description = "SSEBench documentation site";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = lib.licenses.asl20;
  };
}
