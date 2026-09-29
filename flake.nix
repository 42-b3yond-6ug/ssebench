{
  description = "SSEBench development shell";

  inputs = {
    nixpkgs.url = "https://channels.nixos.org/nixpkgs-unstable/nixexprs.tar.xz";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          packages = [
            # languages required
            pkgs.python3 # Infra
            pkgs.go # Tool layer
            pkgs.typst # Report generation
            pkgs.bun # WebUI

            # tools required
            pkgs.uv # Python package manager
            pkgs.just # SSEBench host entrypoint
            pkgs.fzf # Interactive selection in bench/test recipes
            pkgs.jq # report + remote recipes
            pkgs.curl # API calls
          ];
        };
      }
    );
}
