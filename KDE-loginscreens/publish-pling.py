#!/usr/bin/env python3
"""Package splash screens and publish them to Pling / store.kde.org."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Missing deps. Install with: pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
IDS_FILE = ROOT / "pling-ids.json"
AUTH_FILE = ROOT / "pling-credentials.json"
GENERATE_ALL = ROOT / "generate-all.py"
DIST_DIR = ROOT / "dist"
PLING = "https://www.opendesktop.org"
STORE = "https://store.kde.org"
WEBSITE = "https://github.com/dgudim/themes"
# Plasma 6 Splashscreens on store.kde.org
CATEGORY_ID = "716"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ANUBIS_PASS = "/.within.website/x/cmd/anubis/api/pass-challenge"

EPILOG = """
credentials:
  put username and password in pling-credentials.json

versions:
  stored as --version in generate-all.py; the generator writes it into metadata.json

examples:
  %(prog)s --dry-run
  %(prog)s --only DysonSphere
  %(prog)s --only Overload --bump --description "Plasma 6 layout fix"
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
    ids: dict[str, str] = {}
    for key, value in json.loads(IDS_FILE.read_text(encoding="utf-8")).items():
        if isinstance(value, dict):
            product_id = str(value.get("id") or "")
        else:
            product_id = str(value)
        if product_id:
            ids[str(key)] = product_id
    return ids


def save_ids(ids: dict[str, str]) -> None:
    IDS_FILE.write_text(json.dumps(ids, indent=4, sort_keys=True) + "\n", encoding="utf-8")


def load_credentials() -> tuple[str, str]:
    if not AUTH_FILE.is_file():
        raise SystemExit(
            f"Missing {AUTH_FILE.name}. Create it with:\n"
            '{\n  "username": "you@example.com",\n  "password": "..."\n}'
        )
    data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    username = str(data.get("username") or data.get("email") or "").strip()
    password = str(data.get("password") or "").strip()
    if not username or not password:
        raise SystemExit(f"{AUTH_FILE.name} must contain username and password.")
    return username, password


def theme_meta(theme_dir: Path) -> dict:
    return json.loads((theme_dir / "metadata.json").read_text(encoding="utf-8"))


def plugin_version(meta: dict) -> str:
    return str(meta.get("KPlugin", {}).get("Version") or "1.0").strip() or "1.0"


def bump_version(version: str) -> str:
    bits = version.split(".")
    for i in range(len(bits) - 1, -1, -1):
        if bits[i].isdigit():
            bits[i] = str(int(bits[i]) + 1)
            return ".".join(bits)
    return f"{version}.1" if version else "1.1"


def generate_all_version(splash_id: str) -> str | None:
    if not GENERATE_ALL.is_file():
        return None
    match = re.search(
        rf'"--id",\s*"{re.escape(splash_id)}",\s*"--version",\s*"([^"]+)"',
        GENERATE_ALL.read_text(encoding="utf-8"),
    )
    return match.group(1).strip() if match else None


def set_generate_all_version(splash_id: str, version: str) -> None:
    if not GENERATE_ALL.is_file():
        raise SystemExit(f"Missing {GENERATE_ALL.name}; versions are stored there.")
    text = GENERATE_ALL.read_text(encoding="utf-8")
    id_token = f'"--id", "{splash_id}"'
    pattern = re.compile(re.escape(id_token) + r'(,\s*"--version",\s*"[^"]*")?')
    replacement = id_token + f',\n            "--version", "{version}"'
    new_text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise SystemExit(f"Could not update --version for {splash_id} in {GENERATE_ALL.name}.")
    GENERATE_ALL.write_text(new_text, encoding="utf-8")


def regenerate_theme(splash_id: str) -> None:
    print(f"  regenerating {splash_id}...", flush=True)
    result = subprocess.run(
        [sys.executable, str(GENERATE_ALL), "--only", splash_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    log = (result.stdout or "") + (result.stderr or "")
    if log:
        print(log, end="" if log.endswith("\n") else "\n", flush=True)
    if result.returncode != 0:
        raise SystemExit(f"Could not regenerate {splash_id}.")


def interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask_yes_no(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{question} [{hint}]: ").strip().lower()
    if not raw:
        return default
    return raw in {"y", "yes"}


def ask_text(question: str, default: str = "", required: bool = False) -> str:
    hint = f" [{default}]" if default else ""
    while True:
        raw = input(f"{question}{hint}: ")
        text = raw.strip() if raw.strip() else default
        if text or not required:
            return text
        print("Please enter a description.")


def resolve_release(
    args: argparse.Namespace, splash_id: str, current: str, is_update: bool, default_description: str
) -> tuple[str, str]:
    version = current
    if args.version:
        version = args.version.strip()
    elif is_update:
        if args.bump:
            version = bump_version(current)
        elif args.no_bump:
            version = current
        elif interactive():
            if ask_yes_no(f"{splash_id} is at {current}. Bump version for this upload?"):
                suggested = bump_version(current)
                version = ask_text("New version", suggested) or suggested
        else:
            raise SystemExit(
                f"{splash_id} is at {current}. Pass --bump or --no-bump when not running interactively."
            )
    description = (args.description or "").strip()
    if not description:
        if interactive():
            description = ask_text("Changelog / description", default_description, required=True)
        elif is_update:
            raise SystemExit(f"{splash_id}: pass --description for the changelog.")
        else:
            description = default_description
    return version, description


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
        tar.add(theme_dir / "metadata.json", arcname="metadata.json")
        tar.add(theme_dir / "contents", arcname="contents")
    return archive


def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def parse_anubis_challenge(html: str) -> dict | None:
    if "anubis_challenge" not in html:
        return None
    raw = None
    script = soup(html).find("script", id="anubis_challenge")
    if script:
        raw = script.get_text() or (script.string or "")
    if not raw or "{" not in raw:
        match = re.search(r'id="anubis_challenge"[^>]*>\s*(\{.*?\})\s*</script>', html, re.S)
        raw = match.group(1) if match else ""
    raw = raw.strip()
    if "{" in raw:
        raw = raw[raw.find("{") :]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def solve_anubis_pow(random_data: str, difficulty: int) -> tuple[int, str]:
    target = "0" * difficulty
    nonce = 0
    while True:
        digest = hashlib.sha256(f"{random_data}{nonce}".encode()).hexdigest()
        if digest.startswith(target):
            return nonce, digest
        nonce += 1


def hidden_fields(page: BeautifulSoup) -> dict[str, str]:
    fields = {}
    for tag in page.select('input[type="hidden"][name]'):
        fields[tag["name"]] = tag.get("value") or ""
    return fields


def control_name(page: BeautifulSoup, needle: str) -> str | None:
    """Return the real name of a form control (input/select) matching needle.

    The add-product form has changed over time: is_original_or_modification used
    to be a radio group and is now a <select>. Match either and use whatever the
    live form actually names it (with or without a trailing []).
    """
    tag = page.find(
        ["select", "input"],
        attrs={"name": re.compile(re.escape(needle))},
    )
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
    seen = set()
    for tag in page.select("#error, .errors, .error, ul.errors li, .help-block, .invalid-feedback"):
        text = tag.get_text(" ", strip=True)
        if text and text not in seen:
            seen.add(text)
            messages.append(text)
    return messages


def product_id_from(text: str) -> str | None:
    match = re.search(r"/p/(\d+)", text)
    return match.group(1) if match else None


def find_login_form(page: BeautifulSoup):
    for candidate in (
        page.find("form", id="form-signin"),
        page.find("form", id="loginForm"),
        page.find("form", class_=re.compile(r"signin|login", re.I)),
        page.find("form", action=re.compile(r"login", re.I)),
    ):
        if candidate:
            return candidate
    password = page.find("input", attrs={"type": "password"})
    return password.find_parent("form") if password else None


def form_fields(form) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in form.find_all(["input", "button"]):
        name = tag.get("name")
        if not name:
            continue
        typ = (tag.get("type") or "text").lower()
        if typ in {"checkbox", "radio"}:
            if tag.has_attr("checked"):
                fields[name] = tag.get("value") or "1"
            continue
        fields[name] = tag.get("value") or ""
    return fields


def collect_form(form) -> dict[str, str]:
    fields: dict[str, str] = {}
    for tag in form.find_all(["input", "textarea", "select", "button"]):
        name = tag.get("name")
        if not name or name == "cancel":
            continue
        if tag.name == "textarea":
            fields[name] = tag.get_text() or ""
            continue
        if tag.name == "select":
            selected = tag.find("option", selected=True)
            if selected is None:
                selected = tag.find("option", attrs={"selected": True})
            if selected is None:
                selected = tag.find("option")
            fields[name] = selected.get("value") if selected else ""
            continue
        typ = (tag.get("type") or "text").lower()
        if typ in {"file", "reset"}:
            continue
        if typ in {"checkbox", "radio"}:
            if tag.has_attr("checked"):
                fields[name] = tag.get("value") or "1"
            continue
        fields[name] = tag.get("value") or ""
    return fields


def find_product_form(page: BeautifulSoup):
    for form in page.find_all("form"):
        if form.find(attrs={"name": "description"}) or form.find(attrs={"name": "version"}):
            return form
    return None


def login_failed(html: str) -> bool:
    lowered = html.lower()
    return any(
        needle in lowered
        for needle in (
            "incorrect login and/or password",
            "incorrect username and/or password",
            "login error",
            "index.login.error.auth",
        )
    )


def logged_in(html: str) -> bool:
    if re.search(r'"userAuth"\s*:\s*1\b', html):
        return True
    if re.search(r"'userAuth'\s*:\s*1\b", html):
        return True
    if re.search(r'href="[^"]*logout', html, re.I):
        return True
    return False


def is_theme_archive(filename: str, theme_id: str) -> bool:
    name = filename.lower()
    prefix = theme_id.lower()
    return (
        name == f"{prefix}.tar.gz"
        or (name.startswith(f"{prefix}.tar-") and name.endswith(".gz"))
        or name == f"{prefix}.tgz"
        or name == f"{prefix}.zip"
    )


def extract_member_id(html: str) -> str | None:
    for pattern in (
        r"/member/(\d+)/",
        r"/member/(\d+)",
        r"member_id['\"]?\s*[:=]\s*['\"]?(\d+)",
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def json_status(response: requests.Response) -> tuple[str | None, str]:
    try:
        payload = response.json()
        status = payload.get("status")
        return (str(status) if status is not None else None, json.dumps(payload)[:800])
    except ValueError:
        return None, response.text[:800]


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

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        response = self.http.request(method, url, **kwargs)
        challenge = parse_anubis_challenge(response.text)
        if not challenge:
            return response
        self.pass_anubis(response.url or url, challenge)
        response = self.http.request(method, url, **kwargs)
        if parse_anubis_challenge(response.text):
            raise SystemExit("Anubis is still blocking requests after the proof-of-work challenge.")
        return response

    def get(self, url: str, **kwargs) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> requests.Response:
        return self.request("POST", url, **kwargs)

    def pass_anubis(self, url: str, challenge: dict) -> None:
        rules = challenge.get("rules") or {}
        payload = challenge.get("challenge") or {}
        algorithm = rules.get("algorithm") or payload.get("method") or "fast"
        difficulty = int(rules.get("difficulty") or payload.get("difficulty") or 0)
        random_data = payload.get("randomData")
        challenge_id = payload.get("id")
        if not random_data or not challenge_id:
            raise SystemExit("Anubis challenge is missing randomData or id.")
        print(f"Passing Anubis check ({algorithm}, difficulty {difficulty})...", flush=True)
        started = time.time()
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        params = {
            "id": challenge_id,
            "redir": url,
        }
        if algorithm == "fast":
            nonce, digest = solve_anubis_pow(random_data, difficulty)
            params.update(
                {
                    "response": digest,
                    "nonce": str(nonce),
                    "elapsedTime": str(int((time.time() - started) * 1000)),
                }
            )
        elif algorithm == "metarefresh":
            time.sleep(difficulty * 0.8)
            params["challenge"] = random_data
        elif algorithm == "preact":
            time.sleep(difficulty * 0.08)
            params["result"] = hashlib.sha256(random_data.encode()).hexdigest()
        else:
            raise SystemExit(f"Unsupported Anubis challenge type: {algorithm}")
        passed = self.http.get(origin + ANUBIS_PASS, params=params)
        if parse_anubis_challenge(passed.text):
            raise SystemExit("Failed to pass the Anubis proof-of-work challenge.")

    def login(self) -> None:
        self.get(f"{PLING}/")
        login_url = f"{PLING}/login/"
        parsed = urlparse(PLING)
        self.http.cookies.set("verified", "1", domain=parsed.hostname, path="/")
        response = self.get(login_url)
        page = soup(response.text)
        form = find_login_form(page)
        if not form:
            title = page.title.get_text(" ", strip=True) if page.title else ""
            raise SystemExit(f"Could not find the Pling login form. Page title: {title or '(empty)'}")
        fields = form_fields(form)
        for extra in page.select('input[name="login_csrf"], input[name="csrf"]'):
            name = extra.get("name")
            if name and (name not in fields or not fields[name]):
                fields[name] = extra.get("value") or ""
        if "email" in fields:
            fields["email"] = self.username
        elif "mail" in fields:
            fields["mail"] = self.username
        else:
            fields["email"] = self.username
        fields["password"] = self.password
        action = form.get("action") or str(response.url or login_url)
        if action.startswith("/"):
            action = f"{PLING}{action}"
        response = self.post(action, data=fields, headers={"Referer": login_url})
        page = soup(response.text)
        if login_failed(response.text) or (
            "login" in urlparse(response.url).path and find_login_form(page)
        ):
            err = page.select_one("#error")
            detail = err.get_text(" ", strip=True) if err else "the site stayed on the login page"
            raise SystemExit(f"Pling login failed. {detail}")
        if not logged_in(response.text) and not self.http.cookies.get("remember_token"):
            home = self.get(f"{PLING}/")
            if not logged_in(home.text) and not self.http.cookies.get("remember_token"):
                raise SystemExit("Pling login did not establish a session.")
            response = home
        self.member_id = extract_member_id(response.text)

    def create_product(self, meta: dict, preview: Path | None, version: str, description: str) -> str:
        plugin = meta["KPlugin"]
        title = sanitize_title(plugin["Name"])
        add_url = f"{PLING}/product/add?catId={CATEGORY_ID}"
        page = soup(self.get(add_url).text)
        fields = hidden_fields(page)
        fields.update(
            {
                "title": title,
                "project_category_id": CATEGORY_ID,
                "description": description or plugin.get("Description") or plugin["Name"],
                "version": version,
                "source_url": WEBSITE,
                "link_1": WEBSITE,
                "preview": "Preview",
            }
        )
        fields[control_name(page, "is_original_or_modification") or "is_original_or_modification"] = "1"
        license_name, license_id = license_choice(page)
        if license_name and license_id:
            fields[license_name] = license_id
        files = None
        preview_handle = None
        if preview and preview.is_file():
            preview_handle = preview.open("rb")
            files = {"image_small_upload": (preview.name, preview_handle, "image/png")}
        try:
            response = self.post(add_url, data=fields, files=files, headers={"Referer": add_url})
        finally:
            if preview_handle:
                preview_handle.close()
        result = soup(response.text)
        errors = form_errors(result)
        if "/product/add" in response.url or errors:
            detail = "; ".join(errors) if errors else f"form was not accepted (still at {response.url})"
            raise SystemExit(f"Could not create Pling product for {plugin['Name']}: {detail}")
        product_id = product_id_from(response.url) or product_id_from(response.text)
        if not product_id:
            product_id = self.find_product_id(title, result)
        if not product_id and self.member_id:
            products = soup(self.get(f"{PLING}/member/{self.member_id}/products/").text)
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

    def update_product_details(self, product_id: str, version: str, description: str) -> None:
        edit_url = f"{PLING}/p/{product_id}/edit"
        response = self.get(edit_url)
        if "/login" in response.url:
            raise SystemExit(f"Not allowed to edit product {product_id}.")
        form = find_product_form(soup(response.text))
        if not form:
            raise SystemExit(f"Could not find the product form on {edit_url}")
        fields = collect_form(form)
        fields["version"] = version
        if description:
            fields["description"] = description
        fields.setdefault("preview", "Save")
        saved = self.post(edit_url, data=fields, headers={"Referer": edit_url})
        errors = form_errors(soup(saved.text))
        if errors:
            raise SystemExit(f"Could not update product {product_id}: {'; '.join(errors)}")
        print(f"  product version set to {version}", flush=True)

    def add_changelog(self, product_id: str, version: str, description: str) -> None:
        text = description.strip() or f"Version {version}"
        if len(text) < 3:
            text = f"Version {version}"
        title = version if len(version) >= 3 else f"Version {version}"
        response = self.post(
            f"{PLING}/p/{product_id}/saveupdateajax",
            data={"title": title, "text": text},
            headers={
                "Referer": f"{PLING}/p/{product_id}/edit",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        status, detail = json_status(response)
        if status not in {"success", "ok"}:
            raise SystemExit(f"Could not add changelog for product {product_id}:\n{detail}")
        print(f"  changelog {title}", flush=True)

    def ppload_from_edit(self, page: str, edit_url: str) -> dict[str, str]:
        upload_url = re.search(r"var fileUri = '(.*?)'", page)
        owner_id = re.search(r"\"owner_id\", '(.*?)'", page)
        client_id = re.search(r"client_id = '(.*?)'", page)
        collection_id = re.search(r'data-ppload-collection-id="(.*?)"', page)
        if not upload_url or not collection_id:
            raise SystemExit(f"Could not find ppload upload fields on {edit_url}")
        return {
            "upload_url": upload_url.group(1),
            "collection_id": collection_id.group(1),
            "owner_id": owner_id.group(1) if owner_id else "",
            "client_id": client_id.group(1) if client_id else "",
        }

    def list_product_files(self, product_id: str, collection_id: str) -> list[dict]:
        headers = {
            "Referer": f"{PLING}/p/{product_id}/edit",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json",
        }
        response = self.get(
            f"{PLING}/p/{product_id}/getfilesajax",
            params={
                "format": "json",
                "ignore_status_code": "1",
                "status": "all",
                "collection_id": collection_id,
                "perpage": "1000",
                "page": "1",
            },
            headers=headers,
        )
        try:
            data = response.json()
            files = data.get("files") if isinstance(data, dict) else None
            if isinstance(files, list):
                return files
        except ValueError:
            pass
        response = self.get(f"{PLING}/p/{product_id}/loadfilesjson", headers=headers)
        try:
            data = response.json()
        except ValueError:
            raise SystemExit(f"Could not list files for product {product_id}: {response.text[:400]}")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            files = data.get("files") or data.get("data") or []
            if isinstance(files, list):
                return files
        return []

    def delete_product_file(self, product_id: str, file_id: str, name: str) -> None:
        response = self.post(
            f"{PLING}/p/{product_id}/deletepploadfile",
            data={"file_id": str(file_id)},
            headers={
                "Referer": f"{PLING}/p/{product_id}/edit",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
        status, detail = json_status(response)
        if status != "ok":
            raise SystemExit(f"Could not delete {name} from product {product_id}:\n{detail}")

    def upload_file(self, product_id: str, archive: Path, splash_id: str, version: str, description: str) -> None:
        edit_url = f"{PLING}/p/{product_id}/edit"
        response = self.get(edit_url)
        if "/login" in response.url:
            raise SystemExit(f"Not allowed to edit product {product_id}.")
        ppload = self.ppload_from_edit(response.text, edit_url)
        collection_id = ppload["collection_id"]

        existing = self.list_product_files(product_id, collection_id)
        names = [str(item.get("name") or item.get("title") or "?") for item in existing]
        print(f"  existing files: {', '.join(names) if names else '(none)'}", flush=True)
        for item in existing:
            name = str(item.get("name") or item.get("title") or "")
            file_id = item.get("id")
            if file_id and is_theme_archive(name, splash_id):
                print(f"  removing {name}...", flush=True)
                self.delete_product_file(product_id, str(file_id), name)

        payload_bytes = archive.read_bytes()
        upload = self.post(
            ppload["upload_url"],
            data={
                "collection_id": collection_id,
                "owner_id": ppload["owner_id"],
                "format": "json",
                "client_id": ppload["client_id"],
                "name": "file",
                "filename": archive.name,
                "version": version,
                "description": description[:140],
            },
            files={"file": (archive.name, payload_bytes, "application/gzip")},
            headers={
                "Referer": edit_url,
                "Origin": PLING,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )
        try:
            payload = upload.json()
        except ValueError:
            raise SystemExit(f"File upload failed for product {product_id}:\n{upload.text[:800]}")
        status = str(payload.get("status") or "")
        uploaded = payload.get("file") if isinstance(payload.get("file"), dict) else {}
        uploaded_name = str(uploaded.get("name") or archive.name)
        if status not in {"success", "ok"}:
            raise SystemExit(f"File upload failed for product {product_id}:\n{json.dumps(payload)[:800]}")
        if is_theme_archive(uploaded_name, splash_id) and uploaded_name.lower() != archive.name.lower():
            raise SystemExit(
                f"Ppload renamed the archive to {uploaded_name} instead of {archive.name}. "
                "Delete leftover files on the product and retry."
            )
        print(f"  uploaded {uploaded_name}", flush=True)


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
    bump = parser.add_mutually_exclusive_group()
    bump.add_argument("--bump", action="store_true", help="Bump the stored version without asking")
    bump.add_argument("--no-bump", action="store_true", help="Keep the stored version without asking")
    parser.add_argument("--version", metavar="X.Y", help="Set this version instead of bumping")
    parser.add_argument("--description", help="Product description and changelog text")
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

    catalog = load_ids()
    if args.map:
        for splash_id, product_id in args.map:
            catalog[splash_id] = product_id
        save_ids(catalog)

    client = None
    if not args.dry_run:
        username, password = load_credentials()
        print("Logging in to Pling...", flush=True)
        client = PlingClient(username, password)
        client.login()
        print("Logged in.", flush=True)

    for theme_dir in themes:
        meta = theme_meta(theme_dir)
        splash_id = meta["KPlugin"]["Id"]
        product_id = catalog.get(splash_id) or ""
        current = generate_all_version(splash_id) or plugin_version(meta)
        is_update = bool(product_id)
        default_description = str(meta["KPlugin"].get("Description") or meta["KPlugin"]["Name"])
        version, description = resolve_release(args, splash_id, current, is_update, default_description)
        if version != current:
            print(f"  {splash_id} {current} -> {version}", flush=True)
            set_generate_all_version(splash_id, version)
            regenerate_theme(splash_id)
            meta = theme_meta(theme_dir)
        print(f"Packing {splash_id} {version}...", flush=True)
        archive = pack_theme(theme_dir)
        print(f"  {archive} ({archive.stat().st_size} bytes)", flush=True)
        if args.dry_run:
            continue
        assert client is not None
        preview = theme_dir / "contents" / "previews" / "splash.png"
        if not product_id:
            if args.update_only:
                print(f"  skipping {splash_id}: no Pling id", flush=True)
                continue
            print("  creating Pling product...", flush=True)
            product_id = client.create_product(
                meta, preview if preview.is_file() else None, version, description
            )
            print(f"  created {store_url(product_id)}", flush=True)
        else:
            client.update_product_details(product_id, version, description)
        client.add_changelog(product_id, version, description)
        print(f"  uploading {archive.name} to {product_id}...", flush=True)
        client.upload_file(product_id, archive, splash_id, version, description)
        catalog[splash_id] = product_id
        save_ids(catalog)
        print(f"  published {store_url(product_id)} ({version})", flush=True)

    if args.dry_run:
        print(f"Archives written to {DIST_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
