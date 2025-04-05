{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pyqt5
    pkgs.python311Packages.opencv4
    pkgs.python311Packages.numpy
    pkgs.ffmpeg
  ];
}
