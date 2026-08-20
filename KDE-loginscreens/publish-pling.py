#!/usr/bin/env python3
"""Package splash screens and publish them to Pling / store.kde.org."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import time
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Missing deps. Install with: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
IDS_FILE = ROOT / "pling-ids.json"
DIST_DIR = ROOT / "dist"
PLING = "https://www.pling.com"
STORE = "https://store.kde.org"
WEBSITE = "https://github.com/dgudim/themes"
# Plasma 6 Splashscreens on store.kde.org
CATEGORY_ID = "716"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

EPILOG = """
credentials:
  export PLING_USERNAME='you@example.com'
  export PLING_PASSWORD='...'

examples:
  %(prog)s --dry-run
  %(prog)s --only DysonSphere
  %(prog)s --map Sphere=1234567
""".strip()


def discover_themes() -> list[Path]:
    themes = []
    for path in sorted(ROOT.iterdir()):
        if (path / "metadata.json").is_file() and (path / "contents" / "splash").is_dir():
            themes.append(path)
    return themes


def load_ids() -> dict[str, str]:
    if not IDS_FILE.is_file():
        return {}
    return {str(key): str(value) for key, value in json.loads(IDS_FILE.read_text(encoding="utf-8")).items()}


def save_ids(ids: dict[str, str]) -> None:
    IDS_FILE.write_text(json.dumps(ids, indent=4, sort_keys=True) + "\n", encoding="utf-8")


def theme_meta(theme_dir: Path) -> dict:
    return json.loads((theme_dir / "metadata.json").read_text(encoding="utf-8"))


def sanitize_title(title: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 /\[\]\.\-_']+", " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 4:
        cleaned = f"{cleaned} splash"
    return cleaned[:60]


def pack_theme(theme_dir: Path) -> Path:
    DIST_DIR.mkdir(exist_ok=True)
    archive = DIST_DIR / f"{theme_dir.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(theme_dir / "metadata.json", arcname=f"{theme_dir.name}/metadata.json")
        tar.add(theme_dir / "contents", arcname=f"{theme_dir.name}/contents")
    return archive


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def hidden_fields(page: BeautifulSoup) -> dict[str, str]:
    fields = {}
    for tag in page.select('input[type="hidden"][name]'):
        fields[tag["name"]] = tag.get("value") or ""
    return fields


def radio_name(page: BeautifulSoup, needle: str) -> str | None:
    tag = page.find("input", attrs={"type": "radio", "name": re.compile(re.escape(needle))})
    if tag and tag.get("name"):
        return str(tag["name"])
    return None


def license_choice(page: BeautifulSoup) -> tuple[str | None, str | None]:
    select = page.find("select", attrs={"name": re.compile("license", re.I)})
    if not select or not select.get("name"):
        return None, None
    gplv3_id = None
    gpl_id = None
    for option in select.find_all("option"):
        value = option.get("value")
        if not value or not str(value).isdigit():
            continue
        label = re.sub(r"[^a-z0-9]+", "", option.get_text(" ", strip=True).lower())
        if "gplv3" in label or "gpl3" in label:
            gplv3_id = str(value)
        elif "gpl" in label and gpl_id is None:
            gpl_id = str(value)
    return str(select["name"]), gplv3_id or gpl_id


def form_errors(page: BeautifulSoup) -> list[str]:
    messages = []
    for tag in page.select(".errors, .error, ul.errors li"):
        text = tag.get_text(" ", strip=True)
        if text:
            messages.append(text)
    return messages


def product_id_from(text: str) -> str | None:
    match = re.search(r"/p/(\d+)", text)
    return match.group(1) if match else None


class PlingClient:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self.member_id: str | None = None
        self.http = requests.Session()
        self.http.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def login(self) -> None:
        self.http.get(f"{PLING}/")
        login_url = f"{PLING}/login/"
        page = soup(self.http.get(login_url).text)
        csrf = page.find("input", attrs={"name": "csrf"})
        if not csrf or not csrf.get("value"):
            raise SystemExit("Could not find login CSRF token. Pling may be blocking this client.")
        response = self.http.post(
            login_url,
            data={
                "csrf": csrf["value"],
                "email": self.username,
                "password": self.password,
                "next": "/",
                "remember_me": "1",
            },
            headers={"Referer": login_url},
        )
        if "Incorrect login and/or password" in response.text:
            raise SystemExit("Pling login failed. Check PLING_USERNAME / PLING_PASSWORD.")
        home = self.http.get(f"{PLING}/")
        match = re.search(r"/member/(\d+)/", home.text)
        self.member_id = match.group(1) if match else None
        if not self.member_id:
            raise SystemExit("Pling login failed. Check PLING_USERNAME / PLING_PASSWORD.")

    def create_product(self, meta: dict, preview: Path | None) -> str:
        plugin = meta["KPlugin"]
        title = sanitize_title(plugin["Name"])
        add_url = f"{PLING}/product/add?catId={CATEGORY_ID}"
        page = soup(self.http.get(add_url).text)
        fields = hidden_fields(page)
        fields.update(
            {
                "title": title,
                "project_category_id": CATEGORY_ID,
                "description": plugin.get("Description") or plugin["Name"],
                "version": "1.0",
                "source_url": WEBSITE,
                "link_1": WEBSITE,
                "preview": "Preview",
            }
        )
        fields[radio_name(page, "is_original_or_modification") or "is_original_or_modification[]"] = "1"
        license_name, license_id = license_choice(page)
        if license_name and license_id:
            fields[license_name] = license_id
        files = None
        preview_handle = None
        if preview and preview.is_file():
            preview_handle = preview.open("rb")
            files = {"image_small_upload": (preview.name, preview_handle, "image/png")}
        try:
            response = self.http.post(add_url, data=fields, files=files, headers={"Referer": add_url})
        finally:
            if preview_handle:
                preview_handle.close()
        result = soup(response.text)
        errors = form_errors(result)
        if "/product/add" in response.url or errors:
            detail = "; ".join(errors) if errors else "form was not accepted"
            raise SystemExit(f"Could not create Pling product for {plugin['Name']}: {detail}")
        product_id = product_id_from(response.url) or product_id_from(response.text)
        if not product_id:
            product_id = self.find_product_id(title, result)
        if not product_id and self.member_id:
            products = soup(self.http.get(f"{PLING}/member/{self.member_id}/products/").text)
            product_id = self.find_product_id(title, products)
        if not product_id:
            raise SystemExit(f"Created product but could not determine Pling id for {plugin['Name']}.")
        return product_id

    def find_product_id(self, title: str, page: BeautifulSoup) -> str | None:
        needle = sanitize_title(title).lower()
        for link in page.find_all("a", href=re.compile(r"/p/\d+")):
            label = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip().lower()
            if needle == label or needle in label:
                return product_id_from(link["href"])
        return None

    def upload_file(self, product_id: str, archive: Path) -> None:
        edit_url = f"{PLING}/p/{product_id}/edit"
        response = self.http.get(edit_url)
        if "/login" in response.url:
            raise SystemExit(f"Not allowed to edit product {product_id}.")
        page = response.text
        upload_url = re.search(r"var fileUri = '(.*?)'", page)
        owner_id = re.search(r"\"owner_id\", '(.*?)'", page)
        client_id = re.search(r"client_id = '(.*?)'", page)
        collection_id = re.search(r'data-ppload-collection-id="(.*?)"', page)
        if not upload_url:
            raise SystemExit(f"Could not find upload URL on {edit_url}")
        with archive.open("rb") as handle:
            upload = self.http.post(
                upload_url.group(1),
                data={
                    "collection_id": collection_id.group(1) if collection_id else "",
                    "id": str(int(time.time())),
                    "owner_id": owner_id.group(1) if owner_id else "",
                    "format": "json",
                    "client_id": client_id.group(1) if client_id else "",
                    "name": "file",
                    "filename": archive.name,
                },
                files={"file": (archive.name, handle, "application/gzip")},
                headers={
                    "Referer": edit_url,
                    "Origin": PLING,
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                },
            )
        try:
            payload = upload.json()
            ok = payload.get("status") == "success"
            detail = json.dumps(payload)[:800]
        except ValueError:
            ok = '"status":"success"' in upload.text
            detail = upload.text[:800]
        if not ok:
            raise SystemExit(f"File upload failed for product {product_id}:\n{detail}")


def parse_map(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected ID=PLINGID")
    splash_id, product_id = value.split("=", 1)
    splash_id = splash_id.strip()
    product_id = product_id.strip()
    if not splash_id or not product_id.isdigit():
        raise argparse.ArgumentTypeError("expected ID=PLINGID")
    return splash_id, product_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", metavar="ID", action="append", help="Publish only this splash id")
    parser.add_argument("--dry-run", action="store_true", help="Pack archives without uploading")
    parser.add_argument(
        "--update-only",
        action="store_true",
        help="Only upload files for ids already in pling-ids.json",
    )
    parser.add_argument(
        "--map",
        metavar="ID=PLINGID",
        action="append",
        type=parse_map,
        help="Record an existing Pling product id before uploading",
    )
    return parser.parse_args()


def store_url(product_id: str) -> str:
    return f"{STORE}/p/{product_id}/"


def main() -> None:
    args = parse_args()
    themes = discover_themes()
    if args.only:
        wanted = set(args.only)
        themes = [path for path in themes if path.name in wanted]
        missing = wanted - {path.name for path in themes}
        if missing:
            raise SystemExit("Unknown splash id(s): " + ", ".join(sorted(missing)))
    if not themes:
        raise SystemExit("No splash themes found.")

    ids = load_ids()
    if args.map:
        for splash_id, product_id in args.map:
            ids[splash_id] = product_id
        save_ids(ids)

    username = os.environ.get("PLING_USERNAME", "")
    password = os.environ.get("PLING_PASSWORD", "")
    client = None
    if not args.dry_run:
        if not username or not password:
            raise SystemExit("Set PLING_USERNAME and PLING_PASSWORD in the environment.")
        print("Logging in to Pling...", flush=True)
        client = PlingClient(username, password)
        client.login()
        print("Logged in.", flush=True)

    for theme_dir in themes:
        meta = theme_meta(theme_dir)
        splash_id = meta["KPlugin"]["Id"]
        print(f"Packing {splash_id}...", flush=True)
        archive = pack_theme(theme_dir)
        print(f"  {archive} ({archive.stat().st_size} bytes)", flush=True)
        if args.dry_run:
            continue
        assert client is not None
        preview = theme_dir / "contents" / "previews" / "splash.png"
        product_id = ids.get(splash_id)
        if not product_id:
            if args.update_only:
                print(f"  skipping {splash_id}: no Pling id", flush=True)
                continue
            print("  creating Pling product...", flush=True)
            product_id = client.create_product(meta, preview if preview.is_file() else None)
            ids[splash_id] = product_id
            save_ids(ids)
            print(f"  created {store_url(product_id)}", flush=True)
        print(f"  uploading {archive.name} to {product_id}...", flush=True)
        client.upload_file(product_id, archive)
        print(f"  published {store_url(product_id)}", flush=True)

    if args.dry_run:
        print(f"Archives written to {DIST_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
