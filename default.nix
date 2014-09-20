with import <nixpkgs> { };


python34Packages.buildPythonPackage {
  name = "nox-HEAD";
  src = ./.;
  buildInputs = [ git python34Packages.pbr makeWrapper ];
  pythonPath =
    [ python34Packages.dogpile_cache
      python34Packages.click
      python34Packages.requests2
      (python34Packages.buildPythonPackage rec {
        name = "characteristic-14.1.0";

        src = fetchurl {
          url = "https://pypi.python.org/packages/source/c/characteristic/characteristic-14.1.0.tar.gz";
          md5 = "68ea7e28997fc57d3631791ec0567a05";
        };
        doCheck = false;
      })
    ];
  postInstall = "wrapProgram $out/bin/nox --prefix PATH : ${nixUnstable}/bin";
}   

# TODO : make this override work
# nox.override (oldAttrs : {
#   src = ./.;
#   pythonPath = oldAttrs.pythonPath ++ [ pythonPackages.requests2 ];
# })
