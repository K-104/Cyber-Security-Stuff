{pkgs}: {
  deps = [
    pkgs.python312Packages.tkinter
    pkgs.tcl
    pkgs.tk
    pkgs.xorg.xauth
    pkgs.xorg.libXScrnSaver
    pkgs.xorg.libXft
    pkgs.xorg.libXext
    pkgs.xorg.libXrender
    pkgs.xorg.libxcb
    pkgs.xorg.libX11
    pkgs.graphviz
  ];
}
