with import <nixpkgs> { };

nox.overrideAttrs (oldAttrs : {
  src = ./.;
  buildInputs = oldAttrs.buildInputs ++ [ git ];
  propagatedBuildInputs = oldAttrs.propagatedBuildInputs ++ [ python3.pkgs.psutil ];
})
