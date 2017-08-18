with import <nixpkgs> { };

nox.overrideAttrs (oldAttrs : {
  src = ./.;
  buildInputs = oldAttrs.buildInputs ++ [ git ];
})
