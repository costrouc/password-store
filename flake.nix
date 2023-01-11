{
  description = "password-store";

  inputs = {
    nixpkgs = { url = "github:nixos/nixpkgs/nixpkgs-unstable"; };
  };

  outputs = inputs@{ self, nixpkgs, ... }:
    let
      pkgs = import nixpkgs { system = "x86_64-linux"; };

      pythonPackages = pkgs.python3Packages;
    in {
      packages.x86_64-linux.default = pythonPackages.buildPythonPackage {
        pname = "rofi-password-store";
        version = "latest";
        format = "pyproject";

        src = ./.;

        postConfigure = ''
          substituteInPlace password_store.py \
            --replace '"rofi"' '"${pkgs.rofi}/bin/rofi"' \
            --replace '"gpg"' '"${pkgs.gnupg}/bin/gpg"' \
            --replace '"xdotool"' '"${pkgs.xdotool}/bin/xdotool"' \
            --replace '"spectacle"' '"${pkgs.spectacle}/bin/spectacle"' \
            --replace '"zbarimg"' '"${pkgs.zbar}/bin/zbarimg"' \
            --replace '"xclip"' '"${pkgs.xclip}/bin/xclip"'
        '';

        buildInputs = [
          pythonPackages.setuptools
        ];

        propagatedBuildInputs = [
          pythonPackages.ruamel-yaml
          pythonPackages.pytesseract
        ];
      };

      apps.x86_64-linux.default = {
        type = "app";
        program = "${self.packages.x86_64-linux.default}/bin/password-store";
      };

      devShell.x86_64-linux = pkgs.mkShell {
        buildInputs = [
          pythonPackages.ruamel-yaml
          pythonPackages.pytesseract
          pkgs.rofi
          pkgs.gnupg
          pkgs.xdotool
          pkgs.spectacle
          pkgs.zbar
          pkgs.xclip
        ];
      };
    };
}
