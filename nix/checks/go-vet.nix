# go vet for every module, against the vendored dependencies of its package.
{ pkgs, perSystem, ... }:
let
  modules = with perSystem.self; [
    ssebench-entrypoint
    ssebench-catalog
    pty-proxy
  ];
in
pkgs.runCommand "go-vet"
  {
    nativeBuildInputs = [ pkgs.go_1_26 ];
    env = {
      CGO_ENABLED = "0";
      GOFLAGS = "-mod=vendor";
      GOTOOLCHAIN = "local";
      GOWORK = "off";
    };
  }
  ''
    export HOME=$TMPDIR GOCACHE=$TMPDIR/go-cache
    ${pkgs.lib.concatMapStrings (pkg: ''
      echo "go vet: ${pkg.pname}"
      cp -R ${pkg.src} $TMPDIR/${pkg.pname}
      chmod -R u+w $TMPDIR/${pkg.pname}
      cd $TMPDIR/${pkg.pname}/${pkg.modRoot}
      ln -s ${pkg.goModules} vendor
      go vet ./...
    '') modules}
    touch $out
  ''
