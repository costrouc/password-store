{
  description = "rofipy";

  inputs = {
    nixpkgs = { url = "github:nixos/nixpkgs/nixpkgs-unstable"; };
  };

  outputs = inputs@{ self, nixpkgs, ... }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };

      pythonPackages = pkgs.python3Packages;
    in {
      packages.x86_64-linux.default = pythonPackages.buildPythonPackage {
        pname = "rofi-pypass";
        version = "latest";
        format = "pyproject";

        src = ./.;

        preConfigurePhase = ''
          substituteInPlace rofi-python-pass.py \
            --replace "\"rofi\"" "${pkgs.rofi}/bin/rofi" \
            --replace "\"gpg\"" "${pkgs.gnupg}/bin/gpg" \
            --replace "\"xdotool\"" "${pkgs.xdotool}/bin/xdotool" \
        '';

        propagatedBuildInputs = [
          pythonPackages.ruamel-yaml
        ];
      };

      devShell.x86_64-linux = pkgs.mkShell {
        buildInputs = [
          pythonPackages.ruamel-yaml
          pkgs.rofi
          pkgs.gnupg
          pkgs.xdotool
        ];
      };
    };
}
