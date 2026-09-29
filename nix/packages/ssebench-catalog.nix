{ pkgs, flake, ... }:
let
  inherit (pkgs) lib;
  root = ../..;
in
pkgs.buildGo126Module {
  pname = "ssebench-catalog";
  inherit (flake.lib) version;
  # The tests load the pilot manifest from the dataset.
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/catalog")
      (root + "/datasets/pilot/manifest.json")
    ];
  };
  modRoot = "catalog";
  vendorHash = "sha256-o1kU3oud2H5bQo2YPz5KZYqpYN/ZXn9qYMaSJnhwhQk=";
  env.CGO_ENABLED = 0;
  ldflags = [
    "-s"
    "-w"
    "-X main.version=${flake.lib.version}"
  ];

  meta = {
    description = "SSEBench task catalog: serves a dataset manifest over HTTP";
    homepage = "https://github.com/42-b3yond-6ug/ssebench";
    license = lib.licenses.asl20;
    mainProgram = "ssebench-catalog";
  };
}
