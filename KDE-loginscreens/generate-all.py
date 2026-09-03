#!/usr/bin/env python3
"""Regenerate every splash screen in this repo from sources/ media."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATOR = ROOT / "generate-splash.py"
SOURCES = ROOT / "sources"

# media filename in sources/, then generate-splash.py flags
SPLASHES: list[tuple[str, list[str]]] = [
    (
        "20d0d1abf7278b9c.webp",
        [
            "--id", "DysonSphere",
            "--version", "1.0.1",
            "--name", "Dyson sphere",
            "--description", "Dyson sphere for Plasma 6",
            "--align", "center",
            "--size", "550",
            "--background", "#1d2838",
            "--footer-text", "We are cookin'",
            "--text-color", "#f18578",
            "--no-spinner",
            "--smooth",
        ],
    ),
    (
        "06bb6068795f734e.mp4",
        [
            "--id", "Sphere",
            "--version", "1.0.1",
            "--name", "Sphere",
            "--description", "Sphere for Plasma 6",
            "--align", "center",
            "--size", "500",
            "--background", "#000000",
            "--footer-text", "Woooooo",
            "--text-color", "#e0e8f1",
            "--smooth",
        ],
    ),
    (
        "Alterra.gif",
        [
            "--id", "Alterra",
            "--version", "2.0.1",
            "--name", "Alterra",
            "--description", "Alterra for Plasma 6",
            "--align", "center",
            "--size", "367",
            "--background", "#000000",
            "--footer-text", "Welcome to Alterra",
            "--no-smooth",
        ],
    ),
    (
        "Lain.gif",
        [
            "--id", "Lain",
            "--version", "2.0.1",
            "--name", "Lain",
            "--description", "Lain for Plasma 6",
            "--align", "center",
            "--size", "367",
            "--background", "#000000",
            "--footer-text", "Everyone's Konnected",
            "--no-smooth",
        ],
    ),
    (
        "0b177a82c9d03c78.mp4",
        [
            "--id", "Penrose",
            "--version", "2.0.1",
            "--name", "Penrose",
            "--description", "Penrose for Plasma 6",
            "--align", "center",
            "--size", "550",
            "--background", "#49294E",
            "--footer-text", "Look at me go",
            "--text-color", "#e76d6e",
            "--smooth",
        ],
    ),
    (
        "GruvboxHexagon1.gif",
        [
            "--id", "GruvboxHexagon1",
            "--version", "1.0.1",
            "--name", "Gruvbox hexagon (variant 1)",
            "--description", "Gruvbox hexagon for Plasma 6",
            "--align", "center",
            "--size", "500",
            "--background", "#282828",
            "--footer-text", "Spinny boi",
            "--smooth",
        ],
    ),
    (
        "GruvboxHexagon2.gif",
        [
            "--id", "GruvboxHexagon2",
            "--version", "1.0.1",
            "--name", "Gruvbox hexagon (variant 2)",
            "--description", "Gruvbox hexagon for Plasma 6",
            "--align", "center",
            "--size", "500",
            "--background", "#282828",
            "--footer-text", "Spinny boi",
            "--smooth",
        ],
    ),
    (
        "GruvboxHexagon3.gif",
        [
            "--id", "GruvboxHexagon3",
            "--version", "1.0.1",
            "--name", "Gruvbox hexagon (variant 3)",
            "--description", "Gruvbox hexagon for Plasma 6",
            "--align", "center",
            "--size", "500",
            "--background", "#282828",
            "--footer-text", "Spinny boi",
            "--smooth",
        ],
    ),
    (
        "MatrixKDE.mp4",
        [
            "--id", "MatrixKDE",
            "--version", "1.0.1",
            "--name", "Matrix code 'Welcome to KDE'",
            "--description", "Matrix for Plasma 6",
            "--align", "fill",
            "--max-size", "1920",
            "--background", "#000",
            "--footer-text", "Follow the white rabbit",
            "--text-color", "#eff0f1",
            "--no-smooth",
        ],
    ),
    (
        "MatrixKDEGlow.mp4",
        [
            "--id", "MatrixKDEGlow",
            "--version", "1.0.1",
            "--name", "Matrix code 'Welcome to KDE' (glowing)",
            "--description", "Matrix for Plasma 6",
            "--align", "fill",
            "--max-size", "1920",
            "--background", "#000",
            "--footer-text", "Follow the white rabbit",
            "--text-color", "#eff0f1",
            "--no-smooth",
        ],
    ),
    (
        "Lagtrain.gif",
        [
            "--id", "Lagtrain",
            "--version", "2.0.1",
            "--name", "Lagtrain",
            "--description", "Lagtrain for Plasma 6",
            "--align", "fill",
            "--max-size", "1920",
            "--background", "#313131",
            "--footer-text", "Welcome to Plasma",
            "--text-color", "#eff0f1",
            "--no-smooth",
        ],
    ),
    (
        "GruvboxRubiksCube.gif",
        [
            "--id", "GruvboxRubiksCube",
            "--version", "1.0.1",
            "--name", "Gruvbox Rubik's cube",
            "--description", "Gruvbox Rubik's cube for Plasma 6",
            "--align", "fill",
            "--max-size", "1920",
            "--background", "#313131",
            "--footer-text", "Welcome to Plasma",
            "--text-color", "#eff0f1",
            "--no-smooth",
        ],
    ),
    (
        "cool_animation_b1_sektor_information_overload_youtube.mp4",
        [
            "--id", "Overload",
            "--version", "2.0.2",
            "--name", "Overload",
            "--description", "Overload for Plasma 6",
            "--align", "fill",
            "--max-size", "1920",
            "--background", "#000",
            "--no-spinner",
            "--no-footer",
            "--no-smooth",
        ],
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        metavar="ID",
        action="append",
        help="Rebuild only this splash id (can be repeated)",
    )
    parser.add_argument("--install", action="store_true", help="Also install each theme")
    return parser.parse_args()


def generate_one(media: str, flags: list[str], splash_id: str, install: bool) -> tuple[str, subprocess.CompletedProcess[str]]:
    cmd = [
        sys.executable,
        str(GENERATOR),
        str(SOURCES / media),
        *flags,
    ]
    if install:
        cmd.append("--install")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return splash_id, result


def main() -> None:
    args = parse_args()
    wanted = set(args.only) if args.only else None
    selected = []
    for media, flags in SPLASHES:
        splash_id = flags[flags.index("--id") + 1]
        if wanted is None or splash_id in wanted:
            selected.append((media, flags, splash_id))

    if wanted is not None:
        known = {flags[flags.index("--id") + 1] for _, flags in SPLASHES}
        unknown = wanted - known
        if unknown:
            raise SystemExit(f"Unknown splash id(s): {', '.join(sorted(unknown))}")
        if not selected:
            raise SystemExit("No matching splashes to generate.")

    missing = [str(SOURCES / media) for media, _, _ in selected if not (SOURCES / media).is_file()]
    if missing:
        raise SystemExit("Missing source media:\n" + "\n".join(missing))

    workers = min(len(selected), os.cpu_count() or 4)
    print(f"Generating {len(selected)} splash(es) with {workers} workers...", flush=True)

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(generate_one, media, flags, splash_id, args.install)
            for media, flags, splash_id in selected
        ]
        for future in as_completed(futures):
            splash_id, result = future.result()
            log = (result.stdout or "") + (result.stderr or "")
            if log:
                if not log.endswith("\n"):
                    log += "\n"
                print(f"--- {splash_id} ---\n{log}", end="", flush=True)
            if result.returncode != 0:
                failures.append(splash_id)
                print(f"FAILED {splash_id}", flush=True)
            else:
                print(f"Done {splash_id}", flush=True)

    if failures:
        raise SystemExit("Failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
