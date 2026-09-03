#!/usr/bin/env python3
"""Generate a Plasma 6 splash screen look-and-feel package from an image or video."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BREEZE_IMAGES = Path(
    "/usr/share/plasma/look-and-feel/org.kde.breeze.desktop/contents/splash/images"
)
INSTALL_DIR = Path.home() / ".local/share/plasma/look-and-feel"

AUTHOR = "kloud"
EMAIL = "dgudim@gmail.com"
SPDX = "dgudim <dgudim@gmail.com>"
WEBSITE = "https://github.com/dgudim/themes"
PREVIEW_WIDTH = 1920
PREVIEW_HEIGHT = 1080

ALIGNMENTS = (
    "fill",
    "center",
    "top",
    "bottom",
    "left",
    "right",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)

FILL_MODES = {
    "fit": "Image.PreserveAspectFit",
    "crop": "Image.PreserveAspectCrop",
    "stretch": "Image.Stretch",
    "pad": "Image.Pad",
}

EPILOG = """
examples (current themes in this repo):
  %(prog)s sphere.gif --id Sphere --name Sphere --align center --size 500 \\
      --background '#000000' --footer-text 'Woooooo' --text-color '#e0e8f1' --smooth

  %(prog)s alterra.gif --id Alterra --name Alterra --align center --size 367 \\
      --background '#000000' --footer-text 'Welcome to Alterra' --no-smooth
""".strip()


def qml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def logo_anchors(align: str) -> str:
    mapping = {
        "fill": "anchors.fill: parent",
        "center": "anchors.centerIn: parent",
        "top": "anchors.horizontalCenter: parent.horizontalCenter\n            anchors.top: parent.top",
        "bottom": "anchors.horizontalCenter: parent.horizontalCenter\n            anchors.bottom: parent.bottom",
        "left": "anchors.verticalCenter: parent.verticalCenter\n            anchors.left: parent.left",
        "right": "anchors.verticalCenter: parent.verticalCenter\n            anchors.right: parent.right",
        "top-left": "anchors.top: parent.top\n            anchors.left: parent.left",
        "top-right": "anchors.top: parent.top\n            anchors.right: parent.right",
        "bottom-left": "anchors.bottom: parent.bottom\n            anchors.left: parent.left",
        "bottom-right": "anchors.bottom: parent.bottom\n            anchors.right: parent.right",
    }
    return mapping[align]


def find_asset(name: str) -> Path:
    candidates = [
        SCRIPT_DIR / "sources" / "assets" / name,
        SCRIPT_DIR / "assets" / name,
        BREEZE_IMAGES / name,
    ]
    candidates.extend(sorted(SCRIPT_DIR.glob(f"*/contents/splash/images/{name}")))
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"Could not find {name}. Place it in {SCRIPT_DIR / 'sources' / 'assets'} or install breeze."
    )


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"{name} is required but was not found in PATH.")
    return path


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Command failed with exit code {exc.returncode}: {' '.join(cmd)}") from exc


def media_frame_count(path: Path) -> int | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_packets",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = result.stdout.strip().split(",")[0]
    try:
        count = int(raw)
    except ValueError:
        return None
    if count <= 0:
        return None
    return count


def convert_to_webp(src: Path, dest: Path, max_size: int) -> None:
    ffmpeg = require_tool("ffmpeg")
    scale = (
        f"scale='min({max_size},iw)':'min({max_size},ih)'"
        f":force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos"
    )
    print(f"Converting {src} -> {dest} (max {max_size}px, 30 fps)", flush=True)
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"fps=30,{scale},format=yuva420p",
            "-pix_fmt",
            "yuva420p",
            "-loop",
            "0",
            "-an",
            "-c:v",
            "libwebp_anim",
            "-quality",
            "97",
            str(dest),
        ]
    )
    print(f"Converted {dest}", flush=True)


def ffmpeg_color(color: str) -> str:
    value = color.strip()
    if value.startswith("#"):
        hex_color = value[1:]
        if len(hex_color) == 3:
            hex_color = "".join(ch * 2 for ch in hex_color)
        return f"0x{hex_color}"
    return value


def overlay_xy(align: str) -> str:
    return {
        "fill": "(W-w)/2:(H-h)/2",
        "center": "(W-w)/2:(H-h)/2",
        "top": "(W-w)/2:0",
        "bottom": "(W-w)/2:H-h",
        "left": "0:(H-h)/2",
        "right": "W-w:(H-h)/2",
        "top-left": "0:0",
        "top-right": "W-w:0",
        "bottom-left": "0:H-h",
        "bottom-right": "W-w:H-h",
    }[align]


def preview_scale_filter(args: argparse.Namespace) -> str:
    flags = "lanczos" if args.smooth else "neighbor"
    if args.align == "fill":
        width, height = PREVIEW_WIDTH, PREVIEW_HEIGHT
    else:
        width = height = args.size or 500
    if args.fill_mode == "stretch":
        return f"scale={width}:{height}:flags={flags}"
    if args.fill_mode == "crop":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase:flags={flags},"
            f"crop={width}:{height}"
        )
    return f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags={flags}"


def write_preview(src: Path, dest: Path, args: argparse.Namespace) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("Skipping preview: ffmpeg not found", flush=True)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames = media_frame_count(src)
    mid = (frames // 2) if frames and frames > 1 else 0
    print(f"Generating preview {src} -> {dest}", flush=True)
    bg = ffmpeg_color(args.background)
    select = f"select='eq(n\\,{mid})',setpts=PTS-STARTPTS," if mid else ""
    run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={bg}:s={PREVIEW_WIDTH}x{PREVIEW_HEIGHT}:d=1:r=1",
            "-i",
            str(src),
            "-filter_complex",
            (
                f"[1:v]{select}format=rgba,{preview_scale_filter(args)}[img];"
                f"[0:v][img]overlay={overlay_xy(args.align)}:shortest=1"
            ),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(dest),
        ]
    )
    print(f"Wrote preview {dest}", flush=True)


def stage_handler(spinner: bool) -> str:
    lines = [
        "    onStageChanged: {",
        "        if (stage == 2) {",
        "            introAnimation.running = true;",
    ]
    if spinner:
        lines += [
            "        } else if (stage == 5) {",
            "            introAnimation.target = busyIndicator;",
            "            introAnimation.from = 1;",
            "            introAnimation.to = 0;",
            "            introAnimation.running = true;",
        ]
    lines += [
        "        }",
        "    }",
    ]
    return "\n".join(lines)


def logo_qml(args: argparse.Namespace, media_name: str) -> str:
    fill = args.align == "fill"
    lines = [
        "        AnimatedImage {",
        "            id: logo",
    ]
    if not fill and args.size:
        lines += [
            f"            readonly property real size: {args.size}",
            "",
        ]
    lines.append(f"            {logo_anchors(args.align)}")
    lines += [
        "",
        "            asynchronous: true",
        f"            source: {qml_string('images/' + media_name)}",
        "            paused: false",
    ]
    if not fill and args.size:
        lines += [
            "            width: size",
            "            height: size",
        ]
    lines += [
        f"            fillMode: {FILL_MODES[args.fill_mode]}",
        f"            smooth: {'true' if args.smooth else 'false'}",
        "        }",
    ]
    return "\n".join(lines)


def spinner_qml(has_footer: bool) -> str:
    if has_footer:
        position = """            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: footer.top
            anchors.bottomMargin: Kirigami.Units.gridUnit"""
    else:
        position = """            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Kirigami.Units.gridUnit * 4"""
    return f"""
        // TODO: port to PlasmaComponents3.BusyIndicator
        Image {{
            id: busyIndicator
{position}
            asynchronous: true
            source: "images/busywidget.svgz"
            sourceSize.height: Kirigami.Units.gridUnit * 2
            sourceSize.width: Kirigami.Units.gridUnit * 2
            RotationAnimator on rotation {{
                id: rotationAnimator
                from: 0
                to: 360
                // Not using a standard duration value because we don't want the
                // animation to spin faster or slower based on the user's animation
                // scaling preferences; it doesn't make sense in this context
                duration: 2000
                loops: Animation.Infinite
                // Don't want it to animate at all if the user has disabled animations
                running: Kirigami.Units.longDuration > 1
            }}
        }}
""".strip("\n")


def footer_qml(text: str, color: str) -> str:
    return f"""
        Row {{
            id: footer
            spacing: Kirigami.Units.largeSpacing
            anchors {{
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
                margins: Kirigami.Units.gridUnit
            }}
            Text {{
                color: {qml_string(color)}
                anchors.verticalCenter: parent.verticalCenter
                text: {qml_string(text)}
                Accessible.name: text
                Accessible.role: Accessible.StaticText
                textFormat: Text.PlainText
            }}
            Image {{
                asynchronous: true
                source: "images/kde.svgz"
                sourceSize.height: Kirigami.Units.gridUnit * 2
                sourceSize.width: Kirigami.Units.gridUnit * 2
            }}
        }}
""".strip("\n")


def render_qml(args: argparse.Namespace, media_name: str) -> str:
    extras: list[str] = [logo_qml(args, media_name)]
    if args.spinner:
        extras.append(spinner_qml(args.footer))
    if args.footer:
        extras.append(footer_qml(args.footer_text, args.text_color))
    content = "\n\n".join(extras)

    return f"""/*
    SPDX-FileCopyrightText: {date.today().year} {SPDX}

    SPDX-License-Identifier: GPL-2.0-or-later
*/

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {{
    id: root
    color: {qml_string(args.background)}

    property int stage

{stage_handler(args.spinner)}

    Item {{
        id: content
        anchors.fill: parent
        opacity: 0

{content}
    }}

    OpacityAnimator {{
        id: introAnimation
        running: false
        target: content
        from: 0
        to: 1
        duration: Kirigami.Units.veryLongDuration * 2
        easing.type: Easing.InOutQuad
    }}
}}
"""


def render_metadata(args: argparse.Namespace) -> str:
    payload = {
        "KPackageStructure": "Plasma/LookAndFeel",
        "KPlugin": {
            "Authors": [
                {
                    "Email": EMAIL,
                    "Name": AUTHOR,
                }
            ],
            "Category": "",
            "Description": args.description,
            "Id": args.id,
            "License": "GPLv3",
            "Name": args.name,
            "Version": args.version,
            "Website": WEBSITE,
        },
        "Keywords": "Desktop;Workspace;Appearance;Look and Feel;Logout;Lock;Suspend;Shutdown;Hibernate;",
        "X-Plasma-APIVersion": "2",
    }
    return json.dumps(payload, indent=4) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Plasma 6 splash screen from an image or video.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("media", type=Path, help="Source image or video")
    parser.add_argument("--id", required=True, help="Package id and folder name next to this script")
    parser.add_argument("--version", default="1.0", help="Package version written to metadata.json")
    parser.add_argument("--name", help="Display name (default: --id)")
    parser.add_argument("--description", help="Plugin description")
    parser.add_argument(
        "--align",
        choices=ALIGNMENTS,
        default="center",
        help="Image alignment (default: center)",
    )
    parser.add_argument(
        "--size",
        type=int,
        help="Pixel size for non-fill alignments (default: 500)",
    )
    parser.add_argument(
        "--fill-mode",
        choices=tuple(FILL_MODES),
        help="Image fill mode (default: crop for fill, fit otherwise)",
    )
    parser.add_argument("--background", default="#000000", help="Background color (default: #000000)")
    parser.add_argument("--text-color", help="Footer text color (default depends on alignment)")
    parser.add_argument("--footer-text", default="Welcome to Plasma", help="Footer caption")
    parser.add_argument("--no-spinner", dest="spinner", action="store_false", help="Hide the busy spinner")
    parser.add_argument("--no-footer", dest="footer", action="store_false", help="Hide the footer row")
    parser.add_argument(
        "--smooth",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Smooth scaling (default: on for centered, off for fill)",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=1080,
        help="Max width/height when encoding (default: 1080, clamped to --size)",
    )
    parser.add_argument("--install", action="store_true", help=f"Also install to {INSTALL_DIR}")
    parser.set_defaults(spinner=True, footer=True)
    args = parser.parse_args(argv)

    args.media = args.media.expanduser().resolve()
    args.name = args.name or args.id
    args.description = args.description or f"{args.name} for Plasma 6"
    args.output = (SCRIPT_DIR / args.id).resolve()
    if args.size is None and args.align != "fill":
        args.size = 500
    if args.fill_mode is None:
        args.fill_mode = "crop" if args.align == "fill" else "fit"
    if args.text_color is None:
        args.text_color = "#eff0f1" if args.align == "fill" else "#e0e8f1"
    if args.smooth is None:
        args.smooth = args.align != "fill"
    if args.size is not None and args.size <= 0:
        parser.error("--size must be a positive integer")
    if args.max_size <= 0:
        parser.error("--max-size must be a positive integer")
    if args.size is not None:
        args.max_size = min(args.max_size, args.size)
    return args


def prepare_media(args: argparse.Namespace, images_dir: Path) -> Path:
    dest = images_dir / "splash.webp"
    convert_to_webp(args.media, dest, args.max_size)
    return dest


def generate(args: argparse.Namespace) -> Path:
    if not args.media.is_file():
        raise SystemExit(f"Media file not found: {args.media}")
    if args.output.exists():
        shutil.rmtree(args.output)

    splash_dir = args.output / "contents" / "splash"
    images_dir = splash_dir / "images"
    images_dir.mkdir(parents=True)

    media_path = prepare_media(args, images_dir)
    if args.spinner:
        shutil.copy2(find_asset("busywidget.svgz"), images_dir / "busywidget.svgz")
    if args.footer:
        shutil.copy2(find_asset("kde.svgz"), images_dir / "kde.svgz")

    (splash_dir / "Splash.qml").write_text(render_qml(args, media_path.name), encoding="utf-8")
    (args.output / "metadata.json").write_text(render_metadata(args), encoding="utf-8")
    (args.output / ".nomedia").write_text("", encoding="utf-8")

    try:
        write_preview(media_path, args.output / "contents" / "previews" / "splash.png", args)
    except SystemExit as exc:
        print(f"Warning: could not write preview: {exc}", file=sys.stderr)

    if args.install:
        dest = INSTALL_DIR / args.id
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(args.output, dest)
        print(f"Installed to {dest}")

    return args.output


def main() -> None:
    out = generate(parse_args())
    print(f"Created splash screen at {out}")


if __name__ == "__main__":
    main()
