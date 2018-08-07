# small utility to gather the attrname of all nixos tests
# this is cpu intensive so instead only process 1/numJobs of the list
{ jobIndex ? 0, numJobs ? 1, disable_blacklist ? false }:
let
  tests = (import <nixpkgs/nixos/release.nix> {
    supportedSystems = [ builtins.currentSystem ];
  }).tests;
  lib = (import <nixpkgs/lib>);
  blacklist = if disable_blacklist then [] else
    # list of patterns of tests to never rebuild
    # they depend on ./. so are rebuilt on each commit
    [ "installer" "containers-.*" "initrd-network-ssh" "boot" "ec2-.*" ];
  enumerate = prefix: name: value:
  # an attr in tests is either { x86_64 = derivation; } or an attrset of such values.
  if lib.any (x: builtins.match x name != null) blacklist then [] else
  if lib.hasAttr builtins.currentSystem value then
    [ {attr="${prefix}${name}"; drv = value.${builtins.currentSystem};} ]
  else
    lib.flatten (lib.attrValues (lib.mapAttrs (enumerate (prefix + name + ".")) value));
  # list of {attr="tests.foo"; drv=...}
  data = enumerate "" "tests" tests;
  # only keep a fraction of the list
  filterFraction = list: (lib.foldl'
    ({n, result}: element: {
      result = if n==jobIndex then result ++ [ element ] else result;
      n = if n+1==numJobs then 0 else n+1;
    })
    { n=0; result = []; }
    list).result;
  myData = filterFraction data;
  evaluable = lib.filter ({attr, drv}: (builtins.tryEval drv).success) myData;
in
  map ({attr, drv}: {inherit attr; drv=drv.drvPath;}) evaluable
      


