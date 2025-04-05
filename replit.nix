{ pkgs }: {
  deps = [
    pkgs.python311
    # Only include essential packages for code editing and minimal functionality
    pkgs.python311Packages.pip
    pkgs.python311Packages.setuptools
    # Removed heavy dependencies that aren't needed for development-only environment
    # You can uncomment these if you need them for specific testing
    # pkgs.python311Packages.pyqt5
    # pkgs.python311Packages.opencv4
    # pkgs.python311Packages.numpy
    # pkgs.ffmpeg
  ];
}