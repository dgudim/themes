#!/usr/bin/venv python3

from pathlib import Path

source_text = Path("gruvbox_colors_extended.txt").read_text()
source_hexes = source_text.strip().split("\n")

out_rgbs = []

for hex_ in source_hexes:
    hex_ = hex_.lstrip("#")
    rgb_ = tuple(str(int(hex_[i : i + 2], 16)) for i in (0, 2, 4))
    out_rgbs.append(rgb_)


Path("rgbs.txt").write_text("\n".join(" ".join(rgb_) for rgb_ in out_rgbs))
