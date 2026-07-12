#!/usr/bin/env python3
"""GUI launcher for Udemy Course Enroller (pywebview + web/index.html)."""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Dict, List, Optional, Tuple

APP_VERSION = "2.0.2"
GITHUB_REPO = "moayadbah/udemy-free-course-enroller"
REPO_URL = f"https://github.com/{GITHUB_REPO}"
RELEASES_URL = f"{REPO_URL}/releases/latest"
LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.expanduser("~"), ".udemy_enroller")
COOKIE_FILE = os.path.join(APP_DIR, ".cookie")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.yaml")
PREFS_FILE = os.path.join(APP_DIR, "gui_prefs.json")

_SYS = platform.system()

# (label shown in the UI, value passed to the driver manager)
BROWSER_OPTIONS: List[Tuple[str, str]] = [
    ("Brave", "brave"),
    ("Chrome", "chrome"),
    ("Edge", "edge"),
    ("Chromium", "chromium"),
]

# Udemy's top-level categories; matched case-insensitively against
# primary_category/primary_subcategory titles by the enroller.
CATEGORY_OPTIONS: List[str] = [
    "Development",
    "Business",
    "Finance & Accounting",
    "IT & Software",
    "Office Productivity",
    "Personal Development",
    "Design",
    "Marketing",
    "Lifestyle",
    "Photography & Video",
    "Health & Fitness",
    "Music",
    "Teaching & Academics",
]

# Common Udemy course languages; values must match the locale's
# simple_english_title (matched case-insensitively).
LANGUAGE_OPTIONS: List[str] = [
    "English",
    "Arabic",
    "Spanish",
    "Portuguese",
    "French",
    "German",
    "Italian",
    "Turkish",
    "Russian",
    "Hindi",
    "Urdu",
    "Indonesian",
    "Japanese",
    "Korean",
    "Simplified Chinese",
    "Polish",
]

SCRAPER_FLAGS: List[Tuple[str, str]] = [
    ("discudemy", "--discudemy"),
    ("idownloadcoupon", "--idownloadcoupon"),
    ("freebiesglobal", "--freebiesglobal"),
    ("tutorialbar", "--tutorialbar"),
    ("coursevania", "--coursevania"),
]

DEFAULT_PREFS: Dict = {
    "ui_language": "en",
    "theme": "dark",
    "browser": None,
    "onboarded": False,
    "scrapers": {
        "discudemy": True,
        "idownloadcoupon": True,
        "freebiesglobal": True,
        "tutorialbar": False,
        "coursevania": False,
    },
    "max_pages": 5,
    "debug": False,
    "auto_run_enabled": False,
    "auto_run_hours": 12,
    "last_run_ts": 0,
}

# Log-line markers → progress counter keys (each marks one processed course)
_PROGRESS_MARKERS: List[Tuple[str, str]] = [
    ("Successfully enrolled:", "enrolled"),
    ("Already enrolled in:", "already"),
    ("language not wanted", "skipped"),
    ("does not have a wanted category", "skipped"),
    ("as it now costs", "expired"),
    ("as it is always FREE", "expired"),
]

_NOTIFY_TEXT = {
    "en": ("Run complete", "Enrolled in {n} new courses{saved}"),
    "ar": ("اكتملت الجولة", "تم التسجيل في {n} دورة جديدة{saved}"),
}


def _cookie_valid() -> bool:
    """Return True if the cookie file exists and contains an access_token."""
    if not os.path.isfile(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE) as f:
            data = json.load(f)
        return "access_token" in data
    except Exception:
        return False


def _load_yaml() -> Optional[Dict]:
    """Load settings.yaml; return None if missing or unreadable."""
    if not os.path.isfile(SETTINGS_FILE):
        return None
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        with open(SETTINGS_FILE) as f:
            return yaml.load(f)
    except Exception:
        return None


def _save_yaml(data: Dict) -> None:
    """Overwrite settings.yaml, preserving YAML formatting."""
    from ruamel.yaml import YAML

    os.makedirs(APP_DIR, exist_ok=True)
    yaml = YAML()
    yaml.default_flow_style = False
    with open(SETTINGS_FILE, "w") as f:
        yaml.dump(data, f)


def _load_prefs() -> Dict:
    """Load remembered GUI preferences merged over defaults."""
    prefs = json.loads(json.dumps(DEFAULT_PREFS))  # deep copy
    try:
        with open(PREFS_FILE) as f:
            saved = json.load(f)
        scrapers = saved.pop("scrapers", None)
        prefs.update(saved)
        if isinstance(scrapers, dict):
            prefs["scrapers"].update(scrapers)
    except Exception:
        pass
    return prefs


def _save_prefs(prefs: Dict) -> None:
    """Persist GUI preferences; failures are non-fatal."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


def _find_enroller_cmd(flags: List[str]) -> List[str]:
    """Return the command list to invoke udemy_enroller with *flags*."""
    if getattr(sys, "frozen", False):
        # Frozen build: re-exec this same bundled executable in worker mode.
        return [sys.executable, "--run-enroller"] + flags
    bin_path = shutil.which("udemy_enroller")
    if bin_path:
        return [sys.executable, bin_path] + flags
    # Not on PATH — inject argv and call main() directly.
    argv = ["udemy_enroller"] + flags
    snippet = (
        f"import sys; sys.argv={argv!r}; from udemy_enroller.cli import main; main()"
    )
    return [sys.executable, "-c", snippet]


def _resource_path(rel: str) -> str:
    """Resolve a bundled resource in both source and frozen builds."""
    base = getattr(sys, "_MEIPASS", PROJECT_DIR)
    return os.path.join(base, rel)


def _notify(title: str, body: str) -> None:
    """Fire a desktop notification; all failures are silent."""
    try:
        if _SYS == "Darwin":
            esc_t = title.replace("\\", "").replace('"', '\\"')
            esc_b = body.replace("\\", "").replace('"', '\\"')
            script = f'display notification "{esc_b}" with title "{esc_t}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        elif _SYS == "Windows":
            esc_t = title.replace("'", "''")
            esc_b = body.replace("'", "''")
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType=WindowsRuntime] > $null;"
                "$t=[Windows.UI.Notifications.ToastNotificationManager]::"
                "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]"
                "::ToastText02);"
                f"$t.GetElementsByTagName('text').Item(0).InnerText='{esc_t}';"
                f"$t.GetElementsByTagName('text').Item(1).InnerText='{esc_b}';"
                "$n=[Windows.UI.Notifications.ToastNotification]::new($t);"
                "[Windows.UI.Notifications.ToastNotificationManager]::"
                "CreateToastNotifier('Udemy Course Enroller').Show($n);"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True,
                timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            subprocess.run(
                ["notify-send", title, body], capture_output=True, timeout=10
            )
    except Exception:
        pass


class Backend:
    """All app logic; pushes events to the web UI, no toolkit imports."""

    def __init__(self):
        """Initialize."""
        self.window = None  # set by main() after create_window
        self.update_tag: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._bridging = False
        self._running = False
        self._prog: Dict = {}
        self._pending_title: Optional[str] = None
        self._reset_progress()

    # ── UI push channel ──────────────────────────────────────────────────

    def push(self, payload: Dict) -> None:
        """Send an event object to the JS side."""
        win = self.window
        if win is None:
            return
        try:
            win.evaluate_js(f"app.push({json.dumps(payload)})")
        except Exception:
            pass

    def push_run_state(self) -> None:
        self.push(
            {"type": "run_state", "running": self._running, "bridging": self._bridging}
        )

    def log_line(self, text: str, tag: Optional[str] = None) -> None:
        self.push({"type": "log", "lines": [{"text": text, "tag": tag}]})

    @staticmethod
    def _tag_for_line(line: str) -> Optional[str]:
        lo = line.lower()
        if any(w in lo for w in ("error", "exception", "failed", "traceback")):
            return "error"
        if any(w in lo for w in ("enrolled", "savings", "saved", "$", "€", "\xa3")):
            return "success"
        if any(
            w in lo for w in ("warning", "already", "expired", "unwanted", "skipping")
        ):
            return "warn"
        if any(
            w in lo for w in ("scraping", "page:", "received link", "total courses")
        ):
            return "info"
        if "======" in line or "statistics" in lo:
            return "stats"
        return None

    # ── State for the UI ─────────────────────────────────────────────────

    def installed_browsers(self) -> List[Dict]:
        """Return only browsers actually present on this machine."""
        try:
            from udemy_enroller.driver_manager import BROWSER_BINARIES
        except Exception:
            return [{"label": lb, "value": v} for lb, v in BROWSER_OPTIONS]
        found = []
        for label, value in BROWSER_OPTIONS:
            for candidate in BROWSER_BINARIES.get(value, {}).get(_SYS, []):
                if os.path.isfile(candidate) or shutil.which(candidate):
                    found.append({"label": label, "value": value})
                    break
        # Never present an empty list — fall back to all options.
        return found or [{"label": lb, "value": v} for lb, v in BROWSER_OPTIONS]

    def filters_from_settings(self) -> Dict:
        data = _load_yaml() or {}
        udemy = data.get("udemy") or {}
        return {
            "languages": [str(v) for v in (udemy.get("languages") or [])],
            "categories": [str(v) for v in (udemy.get("categories") or [])],
        }

    def save_filters(self, languages: List[str], categories: List[str]) -> None:
        """
        Write filters to settings.yaml, guaranteeing all keys exist.

        The enroller's Settings loader reads email/password/zipcode by key and
        prompts on the console if settings.yaml is missing entirely. Writing a
        complete file (with null creds when unset) means the packaged app never
        blocks on a hidden console prompt — it relies on the bridged cookie.
        """
        data = _load_yaml() or {}
        udemy = data.get("udemy") or {}
        udemy.setdefault("email", None)
        udemy.setdefault("password", None)
        udemy.setdefault("zipcode", None)
        udemy["languages"] = self._clean_list(languages)
        udemy["categories"] = self._clean_list(categories)
        data["udemy"] = udemy
        _save_yaml(data)

    @staticmethod
    def _clean_list(values: List[str]) -> List[str]:
        """Strip, split Arabic/ASCII commas, and deduplicate case-insensitively."""
        out: List[str] = []
        seen = set()
        for value in values:
            for part in str(value).replace("،", ",").split(","):
                text = part.strip()
                if text and text.lower() not in seen:
                    out.append(text)
                    seen.add(text.lower())
        return out

    # ── Login (bridge) ───────────────────────────────────────────────────

    def start_login(self) -> Dict:
        with self._lock:
            if self._bridging or self._running:
                return {"error": "busy"}
            self._bridging = True
        prefs = _load_prefs()
        browsers = self.installed_browsers()
        browser = prefs.get("browser") or browsers[0]["value"]
        if browser not in [b["value"] for b in browsers]:
            browser = browsers[0]["value"]
        self._stop_event.clear()
        self.push_run_state()
        threading.Thread(target=self._run_bridge, args=(browser,), daemon=True).start()
        return {"ok": True}

    def _run_bridge(self, browser: str) -> None:
        """Worker: launch the browser, poll for auth cookies, save them."""
        driver = None
        try:
            from udemy_enroller.driver_manager import DriverManager

            self.log_line(f"Launching {browser} for login…\n", "info")
            try:
                dm = DriverManager(browser=browser, cloudflare_bypass=True)
            except Exception as exc:
                self.log_line(
                    f"Could not start {browser}: {exc}\n"
                    "Make sure that browser is installed.\n",
                    "error",
                )
                return

            driver = dm.driver
            driver.get("https://www.udemy.com/")
            self.log_line("Waiting for you to log in (up to 5 minutes)…\n", "info")

            cookies = self._poll_for_login_cookies(driver)
            self._handle_bridge_result(cookies)
        except Exception as exc:
            self.log_line(f"Bridge error: {exc}\n", "error")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            self._bridging = False
            self.push_run_state()
            self.push({"type": "login", "logged_in": _cookie_valid()})

    def _poll_for_login_cookies(self, driver) -> dict:
        """Poll the browser until the access_token cookie appears or time runs out."""
        deadline = time.time() + 300
        cookies: dict = {}
        while time.time() < deadline and not self._stop_event.is_set():
            try:
                cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            except Exception:
                break  # browser closed or on an unreadable page
            if "access_token" in cookies:
                break
            time.sleep(2)
        return cookies

    def _handle_bridge_result(self, cookies: dict) -> None:
        """Report the login outcome and save the cookies when they are complete."""
        if self._stop_event.is_set():
            self.log_line("Login cancelled.\n", "warn")
            return
        if "access_token" not in cookies:
            self.log_line(
                "Timed out waiting for login. Try logging in again.\n", "warn"
            )
            return

        missing = [
            c for c in ("access_token", "client_id", "csrftoken") if c not in cookies
        ]
        if missing:
            self.log_line(
                f"Almost — still missing {missing}. Make sure you are on the "
                "Udemy homepage, then try again.\n",
                "warn",
            )
            return

        os.makedirs(APP_DIR, exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            f.write(json.dumps(cookies))
        self.log_line("Saved your login — you're ready to enroll!\n", "success")

    # ── Enrollment ───────────────────────────────────────────────────────

    def _build_flags(self, prefs: Dict) -> List[str]:
        flags: List[str] = []
        scrapers = prefs.get("scrapers") or {}
        for name, flag in SCRAPER_FLAGS:
            if scrapers.get(name):
                flags.append(flag)
        pages = prefs.get("max_pages") or 5
        flags += ["--max-pages", str(int(pages))]
        if prefs.get("debug"):
            flags.append("--debug")
        return flags

    def start_enrollment(self) -> Dict:
        if not _cookie_valid():
            return {"error": "not_logged_in"}
        with self._lock:
            if self._running or self._bridging:
                return {"error": "busy"}
            self._running = True

        prefs = _load_prefs()
        # Guarantee a complete settings.yaml (with null email/password/zipcode)
        # exists before launching the enroller. Otherwise, on a machine where
        # no filter was ever set, the enroller's Settings loader falls through
        # to an interactive input() prompt for the email — which raises
        # EOFError in the windowed frozen app (no console/stdin). Enrollment
        # relies on the bridged cookie, not these credentials.
        try:
            current = self.filters_from_settings()
            self.save_filters(current["languages"], current["categories"])
        except Exception as exc:
            self.log_line(f"Warning: could not write settings: {exc}\n", "warn")
        self._reset_progress()
        self._stop_event.clear()
        self.push_run_state()

        cmd = _find_enroller_cmd(self._build_flags(prefs))
        self.log_line(f"$ {' '.join(cmd)}\n\n", "dim")
        threading.Thread(target=self._stream_enroller, args=(cmd,), daemon=True).start()
        return {"ok": True}

    def _stream_enroller(self, cmd: List[str]) -> None:
        """
        Run the enroller as a child process and mirror its log into the GUI.

        We tail the enroller's ``app.log`` rather than the child's stdout: in a
        frozen windowed build there is no console, so the child's stdout is
        unreliable, but the file handler always writes. This keeps one code path
        for both the source run and the packaged executable.
        """
        log_path = os.path.join(APP_DIR, "app.log")
        try:
            offset = os.path.getsize(log_path)
        except OSError:
            offset = 0

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        # In a frozen build __file__ lives in a temp extraction dir; let the
        # child inherit the cwd instead. Avoid a console flashing up on Windows.
        work_dir = None if getattr(sys, "frozen", False) else PROJECT_DIR
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if _SYS == "Windows" else 0
        )
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=work_dir,
                env=env,
                creationflags=creationflags,
            )
            offset = self._pump_enroller_log(log_path, offset)
            self._process.wait()
            self._drain_log(log_path, offset)  # catch the final lines
            code = self._process.returncode
            if code not in (0, None) and not self._stop_event.is_set():
                self.log_line(
                    f"\nEnroller exited with code {code}. See {log_path}\n", "error"
                )
        except Exception as exc:
            self.log_line(f"Launcher error: {exc}\n", "error")
        finally:
            self._process = None
            self._enrollment_finished()

    def _pump_enroller_log(self, log_path: str, offset: int) -> int:
        """Tail the log while the child runs; terminate it if Stop was pressed."""
        while True:
            offset = self._drain_log(log_path, offset)
            if self._stop_event.is_set():
                try:
                    self._process.terminate()
                except Exception:
                    pass
                return offset
            if self._process.poll() is not None:
                return offset
            time.sleep(0.4)

    def _drain_log(self, log_path: str, offset: int) -> int:
        """Push new log lines to the UI since *offset*; return the new offset."""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                new_text = f.read()
                offset = f.tell()
        except OSError:
            return offset
        if not new_text:
            return offset
        lines = []
        for line in new_text.splitlines(keepends=True):
            self._parse_progress(line)
            lines.append({"text": line, "tag": self._tag_for_line(line)})
        self.push({"type": "log", "lines": lines})
        self.push({"type": "progress", "data": self._prog})
        return offset

    def _enrollment_finished(self) -> None:
        self._running = False
        self.push_run_state()
        self.log_line("\n─── Run complete ───\n", "stats")

        prefs = _load_prefs()
        prefs["last_run_ts"] = time.time()
        _save_prefs(prefs)

        p = self._prog
        enrolled = (
            p["stats_enrolled"] if p["stats_enrolled"] is not None else p["enrolled"]
        )
        savings = p["savings"] or ""
        self.push(
            {"type": "result", "data": {"enrolled": enrolled, "savings": savings}}
        )
        if enrolled or p["total"]:
            lang = prefs.get("ui_language", "en")
            title, body = _NOTIFY_TEXT.get(lang, _NOTIFY_TEXT["en"])
            saved = f" — {savings}" if savings else ""
            _notify(title, body.format(n=enrolled, saved=saved))

    def stop(self) -> Dict:
        self._stop_event.set()
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass
        return {"ok": True}

    # ── Progress tracking ────────────────────────────────────────────────

    def _reset_progress(self) -> None:
        self._pending_title = None
        self._prog = {
            "total": 0,
            "processed": 0,
            "enrolled": 0,
            "already": 0,
            "skipped": 0,
            "expired": 0,
            "stats_enrolled": None,
            "savings": None,
        }

    def _parse_progress(self, line: str) -> None:
        """Update counters (and course links) from a fresh enroller log line."""
        p = self._prog
        if "Total courses this time:" in line:
            try:
                p["total"] += int(line.rsplit(":", 1)[1].strip())
            except ValueError:
                pass
            return
        if "Course link:" in line:
            url = line.split("Course link:", 1)[1].strip()
            if url:
                title = self._pending_title or url
                self.push({"type": "course", "data": {"title": title, "url": url}})
            return
        match = re.search(r"Successfully enrolled: '(.+)'", line)
        if match:
            self._pending_title = match.group(1)
        for marker, key in _PROGRESS_MARKERS:
            if marker in line:
                p[key] += 1
                p["processed"] += 1
                return
        self._parse_stats(line)

    def _parse_stats(self, line: str) -> None:
        """Capture totals from the final Run Statistics table."""
        match = re.search(r"Enrolled:\s{2,}(\d+)", line)
        if match:
            self._prog["stats_enrolled"] = int(match.group(1))
            return
        match = re.search(r"Savings:\s{2,}(\S+)", line)
        if match:
            self._prog["savings"] = match.group(1)

    # ── Background tasks ─────────────────────────────────────────────────

    def on_started(self) -> None:
        """Called by webview.start once the window exists."""
        threading.Thread(target=self._check_updates, daemon=True).start()
        threading.Thread(target=self._auto_run_loop, daemon=True).start()

    def _check_updates(self) -> None:
        """Quietly look for a newer GitHub release."""
        try:
            import requests

            resp = requests.get(LATEST_API, timeout=5)
            tag = resp.json().get("tag_name", "")
            if self._is_newer(tag, APP_VERSION):
                self.update_tag = tag
                self.push({"type": "update", "tag": tag})
        except Exception:
            pass

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        def parse(version: str) -> Tuple[int, ...]:
            parts = re.findall(r"\d+", version)[:3]
            return tuple(int(p) for p in parts) if parts else (0,)

        return parse(remote) > parse(local)

    def _auto_run_loop(self) -> None:
        """Start a run on schedule while the app is open (and logged in)."""
        while True:
            time.sleep(60)
            try:
                prefs = _load_prefs()
                if not prefs.get("auto_run_enabled"):
                    continue
                if self._running or self._bridging or not _cookie_valid():
                    continue
                interval = float(prefs.get("auto_run_hours") or 12) * 3600
                if time.time() - float(prefs.get("last_run_ts") or 0) >= interval:
                    self.log_line("Scheduled run starting…\n", "info")
                    self.start_enrollment()
            except Exception:
                pass


class Api:
    """Methods exposed to JavaScript via pywebview's js_api."""

    def __init__(self, backend: Backend):
        """Initialize."""
        self._backend = backend  # underscore-prefixed → not exposed to JS

    def get_state(self, args=None) -> Dict:
        """Full snapshot the UI needs on load."""
        b = self._backend
        return {
            "state": {
                "logged_in": _cookie_valid(),
                "running": b._running,
                "bridging": b._bridging,
                "version": APP_VERSION,
                "releases_url": RELEASES_URL,
                "repo_url": REPO_URL,
                "lang_options": LANGUAGE_OPTIONS,
                "cat_options": CATEGORY_OPTIONS,
                "browsers": b.installed_browsers(),
            },
            "prefs": _load_prefs(),
            "filters": b.filters_from_settings(),
            "update_tag": b.update_tag,
        }

    def save_prefs(self, args) -> Dict:
        """Persist UI preferences sent from JS."""
        prefs = (args or {}).get("prefs") or {}
        merged = _load_prefs()
        scrapers = prefs.pop("scrapers", None)
        merged.update(prefs)
        if isinstance(scrapers, dict):
            merged["scrapers"].update(scrapers)
        _save_prefs(merged)
        return {"ok": True}

    def save_filters(self, args) -> Dict:
        """Persist language/category filters to settings.yaml."""
        args = args or {}
        self._backend.save_filters(
            args.get("languages") or [], args.get("categories") or []
        )
        return {"ok": True}

    def start_login(self, args=None) -> Dict:
        """Open the login browser and wait for Udemy cookies."""
        return self._backend.start_login()

    def start_enrollment(self, args=None) -> Dict:
        """Kick off an enrollment run."""
        return self._backend.start_enrollment()

    def stop(self, args=None) -> Dict:
        """Stop the current run or login wait."""
        return self._backend.stop()

    def open_url(self, args) -> Dict:
        """Open a link in the user's default browser."""
        url = (args or {}).get("url") or ""
        if url.startswith("http://") or url.startswith("https://"):
            webbrowser.open(url)
        return {"ok": True}


def main() -> None:
    """Entrypoint: launch the GUI, or run a worker when re-exec'd while frozen."""
    if len(sys.argv) > 1 and sys.argv[1] == "--run-enroller":
        # The frozen build re-exec's itself in this mode to run the enroller as a
        # child process (so Stop works and logs stream back), since there is no
        # external `python`/`udemy_enroller` to call on an end user's machine.
        sys.argv = ["udemy_enroller"] + sys.argv[2:]
        from udemy_enroller.cli import main as cli_main

        cli_main()
        return

    import webview

    backend = Backend()
    window = webview.create_window(
        "Udemy Course Enroller",
        url=_resource_path(os.path.join("web", "index.html")),
        js_api=Api(backend),
        width=1080,
        height=780,
        min_size=(940, 660),
        background_color="#0a0d13",
    )
    backend.window = window
    webview.start(backend.on_started)


if __name__ == "__main__":
    main()
