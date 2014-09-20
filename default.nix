with import <nixpkgs> { };
let characteristic = python3Packages.buildPythonPackage rec {
  name = "characteristic-14.1.0";
  src = fetchurl {
    url = "https://pypi.python.org/packages/source/c/characteristic/characteristic-14.1.0.tar.gz";
    md5 = "68ea7e28997fc57d3631791ec0567a05";
  };
  doCheck = false;
};
  newDeps = [ python3Packages.requests2 characteristic ];

in stdenv.lib.overrideDerivation nox (oldAttrs : {
  src = ./.;
  pythonPath = oldAttrs.pythonPath ++ newDeps;
  nativeBuildInputs = oldAttrs.nativeBuildInputs ++ newDeps;
})
