{ pkgs }: {
  deps = [
    pkgs.python310
    pkgs.python310Packages.pip
    pkgs.python310Packages.setuptools
    # Add additional packages as needed, but carefully
  ];
}