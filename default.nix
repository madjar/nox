with import <nixpkgs> { };

stdenv.lib.overrideDerivation nox (oldAttrs : {
  src = ./.;
  buildInputs = oldAttrs.buildInputs ++ [ git ];
})
