#!/usr/bin/env python3
"""GUI launcher for Udemy Course Enroller."""

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.expanduser("~"), ".udemy_enroller")
COOKIE_FILE = os.path.join(APP_DIR, ".cookie")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.yaml")

_SYS = platform.system()

if _SYS == "Darwin":
    _UI_FONT = "Helvetica Neue"
    _MONO_FONT = "Menlo"
elif _SYS == "Windows":
    _UI_FONT = "Segoe UI"
    _MONO_FONT = "Consolas"
else:
    _UI_FONT = "DejaVu Sans"
    _MONO_FONT = "DejaVu Sans Mono"

# (label shown in the dropdown, value passed to bridge_cookies.py)
# These browsers are used only for the interactive login/bridge step; the
# Cloudflare-bypass attach logic in driver_manager.py supports all of them.
BROWSER_OPTIONS: List[Tuple[str, str]] = [
    ("Brave", "brave"),
    ("Chrome", "chrome"),
    ("Edge", "edge"),
    ("Chromium", "chromium"),
]


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


def _settings_exist() -> bool:
    """Return True if settings.yaml has been created."""
    return os.path.isfile(SETTINGS_FILE)


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


class App(tk.Tk):
    """Main application window."""

    def __init__(self):
        """Initialize."""
        super().__init__()
        self.title("Udemy Course Enroller")
        self.geometry("980x770")
        self.minsize(860, 660)
        self.configure(bg="#f0f0f0")
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._bridging = False
        self._build_ui()
        self._refresh_status()
        self._load_filter_settings()
        self._update_bridge_label()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._init_styles()

        wrap = ttk.Frame(self, padding=(16, 14))
        wrap.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            wrap,
            text="Udemy Course Enroller",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            wrap,
            text="Auto-enroll in free Udemy courses using coupon scrapers",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        notebook = ttk.Notebook(wrap)
        notebook.pack(fill=tk.BOTH, expand=True)

        setup_tab = ttk.Frame(notebook, padding=14)
        run_tab = ttk.Frame(notebook, padding=14)
        notebook.add(setup_tab, text="  Setup  ")
        notebook.add(run_tab, text="  Run  ")

        self._build_setup_tab(setup_tab)
        self._build_run_tab(run_tab)

    def _init_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#f0f0f0", font=(_UI_FONT, 12))
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabel", background="#f0f0f0", font=(_UI_FONT, 12))
        style.configure("TCheckbutton", background="#f0f0f0", font=(_UI_FONT, 11))
        style.configure("TSpinbox", font=(_UI_FONT, 11))
        style.configure("TEntry", font=(_UI_FONT, 11))
        style.configure("TCombobox", font=(_UI_FONT, 11))
        style.configure("TButton", font=(_UI_FONT, 11), padding=6)
        style.configure("TNotebook", background="#f0f0f0")
        style.configure("TNotebook.Tab", font=(_UI_FONT, 11, "bold"), padding=(18, 8))
        style.configure(
            "TLabelframe", background="#f0f0f0", borderwidth=1, relief="solid"
        )
        style.configure(
            "TLabelframe.Label",
            background="#f0f0f0",
            font=(_UI_FONT, 12, "bold"),
            foreground="#333333",
        )
        style.configure(
            "Title.TLabel",
            font=(_UI_FONT, 17, "bold"),
            background="#f0f0f0",
        )
        style.configure(
            "Hint.TLabel",
            font=(_UI_FONT, 10),
            foreground="#666666",
            background="#f0f0f0",
        )
        style.configure("Status.TLabel", font=(_UI_FONT, 11), background="#f0f0f0")
        style.configure(
            "Step.TLabel",
            font=(_UI_FONT, 11),
            foreground="#333333",
            background="#f0f0f0",
        )
        style.configure(
            "StepLead.TLabel",
            font=(_UI_FONT, 12, "bold"),
            foreground="#1976d2",
            background="#f0f0f0",
        )
        style.configure("Primary.TButton", font=(_UI_FONT, 12, "bold"), padding=8)
        style.configure("Danger.TButton", font=(_UI_FONT, 11), padding=6)
        style.map(
            "Primary.TButton",
            foreground=[("active", "white"), ("!disabled", "white")],
            background=[("active", "#1565c0"), ("!disabled", "#1976d2")],
        )
        style.map(
            "Danger.TButton",
            foreground=[("active", "white"), ("disabled", "#999999")],
            background=[
                ("active", "#b71c1c"),
                ("disabled", "#dddddd"),
                ("!disabled", "#d32f2f"),
            ],
        )

    # ── Setup tab ────────────────────────────────────────────────────────────

    def _build_setup_tab(self, parent: ttk.Frame) -> None:
        # Ordered for a first-time user: explain the flow, then the one required
        # choice (browser), then optional tweaks, then the readiness check last.
        self._build_getting_started_section(parent)
        self._build_browser_section(parent)
        self._build_scraper_section(parent)
        self._build_filter_section(parent)
        self._build_status_section(parent)

    def _build_getting_started_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" Getting Started ", padding=10)
        box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            box,
            text="New here? Three steps to your first free courses:",
            style="StepLead.TLabel",
        ).pack(anchor="w")

        steps = (
            "1.  Pick your Login Browser below (whichever you have installed).\n"
            '2.  Open the "Run" tab and click "Bridge Cookies". A browser opens —\n'
            "      log in to Udemy with your email, password, and the 6-digit code\n"
            "      it emails you. This is what turns the status below green.\n"
            '3.  Back on the "Run" tab, click "Start Enrollment" and watch the log.'
        )
        ttk.Label(box, text=steps, style="Step.TLabel", justify=tk.LEFT).pack(
            anchor="w", pady=(4, 4)
        )

        ttk.Label(
            box,
            text="Logged-in sessions last days — repeat step 2 only when needed.",
            style="Hint.TLabel",
        ).pack(anchor="w")

    def _build_status_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" Setup Status ", padding=10)
        box.pack(fill=tk.X, pady=(0, 10))

        r1 = ttk.Frame(box)
        r1.pack(fill=tk.X, pady=1)
        self._dot_settings = tk.Label(
            r1, text="●", font=(_UI_FONT, 14), bg="#f0f0f0", fg="#999999"
        )
        self._dot_settings.pack(side=tk.LEFT)
        self._lbl_settings = ttk.Label(r1, text="Checking…", style="Status.TLabel")
        self._lbl_settings.pack(side=tk.LEFT, padx=6)
        ttk.Button(r1, text="Refresh", command=self._refresh_status).pack(side=tk.RIGHT)

        r2 = ttk.Frame(box)
        r2.pack(fill=tk.X, pady=1)
        self._dot_cookie = tk.Label(
            r2, text="●", font=(_UI_FONT, 14), bg="#f0f0f0", fg="#999999"
        )
        self._dot_cookie.pack(side=tk.LEFT)
        self._lbl_cookie = ttk.Label(r2, text="Checking…", style="Status.TLabel")
        self._lbl_cookie.pack(side=tk.LEFT, padx=6)

    def _build_browser_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" Login Browser ", padding=10)
        box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            box,
            text=(
                "Used by the Bridge Cookies step to log in past Cloudflare. "
                "Enrollment itself uses fast REST mode (no browser window)."
            ),
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(box)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Browser:").pack(side=tk.LEFT)
        browser_labels = [label for label, _ in BROWSER_OPTIONS]
        self._var_browser_label = tk.StringVar(value=browser_labels[0])
        combo = ttk.Combobox(
            row,
            textvariable=self._var_browser_label,
            values=browser_labels,
            state="readonly",
            width=18,
        )
        combo.pack(side=tk.LEFT, padx=8)
        combo.bind("<<ComboboxSelected>>", self._update_bridge_label)

    def _build_scraper_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" Scrapers ", padding=10)
        box.pack(fill=tk.X, pady=(0, 10))

        self._var_discudemy = tk.BooleanVar(value=True)
        self._var_idc = tk.BooleanVar(value=True)
        self._var_fbg = tk.BooleanVar(value=True)
        self._var_tutbar = tk.BooleanVar(value=False)
        self._var_cvania = tk.BooleanVar(value=False)

        row1 = ttk.Frame(box)
        row1.pack(fill=tk.X)
        ttk.Checkbutton(row1, text="discudemy", variable=self._var_discudemy).pack(
            side=tk.LEFT, padx=(0, 20)
        )
        ttk.Checkbutton(row1, text="idownloadcoupon", variable=self._var_idc).pack(
            side=tk.LEFT, padx=(0, 20)
        )
        ttk.Checkbutton(row1, text="freebiesglobal", variable=self._var_fbg).pack(
            side=tk.LEFT
        )

        row2 = ttk.Frame(box)
        row2.pack(fill=tk.X, pady=(4, 0))
        ttk.Checkbutton(
            row2, text="tutorialbar  ⚠ offline", variable=self._var_tutbar
        ).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(
            row2, text="coursevania  ⚠ JS-blocked", variable=self._var_cvania
        ).pack(side=tk.LEFT)

        opts = ttk.Frame(box)
        opts.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(opts, text="Max pages per scraper:").pack(side=tk.LEFT)
        self._var_pages = tk.IntVar(value=5)
        ttk.Spinbox(opts, from_=1, to=50, width=5, textvariable=self._var_pages).pack(
            side=tk.LEFT, padx=8
        )
        self._var_debug = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Debug logging", variable=self._var_debug).pack(
            side=tk.LEFT, padx=(16, 0)
        )

    def _build_filter_section(self, parent: ttk.Frame) -> None:
        box = ttk.LabelFrame(parent, text=" Course Filters ", padding=10)
        box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            box,
            text="Leave blank to accept all. Saved to settings.yaml before each run.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        grid = ttk.Frame(box)
        grid.pack(fill=tk.X)

        ttk.Label(grid, text="Languages:").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self._var_languages = tk.StringVar()
        ttk.Entry(grid, textvariable=self._var_languages).grid(
            row=0, column=1, sticky="ew", pady=3
        )
        ttk.Label(grid, text="e.g. English, Spanish", style="Hint.TLabel").grid(
            row=0, column=2, sticky="w", padx=(10, 0), pady=3
        )

        ttk.Label(grid, text="Categories:").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self._var_categories = tk.StringVar()
        ttk.Entry(grid, textvariable=self._var_categories).grid(
            row=1, column=1, sticky="ew", pady=3
        )
        ttk.Label(grid, text="e.g. Development, Design", style="Hint.TLabel").grid(
            row=1, column=2, sticky="w", padx=(10, 0), pady=3
        )

        grid.columnconfigure(1, weight=1)

    # ── Run tab ──────────────────────────────────────────────────────────────

    def _build_run_tab(self, parent: ttk.Frame) -> None:
        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(0, 10))

        self._btn_bridge = ttk.Button(
            actions,
            text="Bridge Cookies",
            command=self._bridge_cookies,
        )
        self._btn_bridge.pack(side=tk.LEFT, padx=(0, 10))
        self._btn_start = ttk.Button(
            actions,
            text="Start Enrollment",
            style="Primary.TButton",
            command=self._start_enrollment,
        )
        self._btn_start.pack(side=tk.LEFT, padx=(0, 6))
        self._btn_stop = ttk.Button(
            actions,
            text="Stop",
            style="Danger.TButton",
            state=tk.DISABLED,
            command=self._stop_enrollment,
        )
        self._btn_stop.pack(side=tk.LEFT)

        log_hdr = ttk.Frame(parent)
        log_hdr.pack(fill=tk.X)
        ttk.Label(log_hdr, text="Log", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(log_hdr, text="Clear log", command=self._clear_log).pack(
            side=tk.RIGHT
        )

        self._log = scrolledtext.ScrolledText(
            parent,
            font=(_MONO_FONT, 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#d4d4d4",
            selectbackground="#264f78",
            state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self._log.tag_configure("error", foreground="#f48771")
        self._log.tag_configure("success", foreground="#89d185")
        self._log.tag_configure("info", foreground="#569cd6")
        self._log.tag_configure("warn", foreground="#dcdcaa")
        self._log.tag_configure("stats", foreground="#c586c0")
        self._log.tag_configure("dim", foreground="#808080")

    # ── Status ───────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        """Re-check whether settings.yaml and the cookie file are present."""
        if _settings_exist():
            self._dot_settings.configure(fg="#43a047")
            self._lbl_settings.configure(text="Settings saved")
        else:
            self._dot_settings.configure(fg="#9e9e9e")
            self._lbl_settings.configure(
                text="Settings: none yet — you'll enter email/password during login"
            )

        if _cookie_valid():
            self._dot_cookie.configure(fg="#43a047")
            self._lbl_cookie.configure(text="Logged in — ready to enroll")
        else:
            self._dot_cookie.configure(fg="#e53935")
            self._lbl_cookie.configure(
                text='Not logged in yet — do step 2 ("Bridge Cookies" on the Run tab)'
            )

    # ── Browser selection ────────────────────────────────────────────────────

    def _selected_browser(self) -> str:
        """Return the browser value for the selected dropdown entry."""
        label = self._var_browser_label.get()
        for opt_label, opt_value in BROWSER_OPTIONS:
            if opt_label == label:
                return opt_value
        return "brave"

    def _update_bridge_label(self, *_) -> None:
        """Reflect the chosen browser in the Bridge Cookies button text."""
        label = self._var_browser_label.get()
        self._btn_bridge.configure(text=f"Bridge Cookies — Login with {label}")

    # ── Filter settings ──────────────────────────────────────────────────────

    def _load_filter_settings(self) -> None:
        """Populate the language/category fields from settings.yaml."""
        data = _load_yaml()
        if data is None:
            return
        udemy = data.get("udemy") or {}
        languages: List[str] = udemy.get("languages") or []
        categories: List[str] = udemy.get("categories") or []
        self._var_languages.set(", ".join(languages))
        self._var_categories.set(", ".join(categories))

    def _save_filter_settings(self) -> None:
        """
        Write filters back to settings.yaml, guaranteeing all keys exist.

        The enroller's Settings loader reads email/password/zipcode by key and
        prompts on the console if settings.yaml is missing entirely. Writing a
        complete file (with null creds when unset) means the packaged app never
        blocks on a hidden console prompt — it relies on the bridged cookie.
        """
        data = _load_yaml() or {}
        udemy = data.get("udemy") or {}

        # Preserve any saved credentials; default the rest so loading never fails.
        udemy.setdefault("email", None)
        udemy.setdefault("password", None)
        udemy.setdefault("zipcode", None)

        # Accept the Arabic comma (،) as a separator too, not just the ASCII one.
        langs_raw = self._var_languages.get().strip().replace("،", ",")
        cats_raw = self._var_categories.get().strip().replace("،", ",")
        udemy["languages"] = (
            [lang.strip() for lang in langs_raw.split(",") if lang.strip()]
            if langs_raw
            else []
        )
        udemy["categories"] = (
            [cat.strip() for cat in cats_raw.split(",") if cat.strip()]
            if cats_raw
            else []
        )

        data["udemy"] = udemy
        _save_yaml(data)

    # ── Bridge cookies ───────────────────────────────────────────────────────

    def _bridge_cookies(self) -> None:
        """Open the chosen browser and capture Udemy auth cookies after login."""
        if self._bridging or self._process is not None:
            return

        browser = self._selected_browser()
        browser_label = self._var_browser_label.get()
        messagebox.showinfo(
            "Bridge Cookies",
            f"{browser_label} will open.\n\n"
            "Log in to Udemy: email, password, and the 6-digit code it emails you.\n\n"
            "As soon as you reach your logged-in Udemy homepage, this app detects it\n"
            "automatically and saves your login — no need to come back and click anything.",
        )

        self._bridging = True
        self._stop_event.clear()
        self._btn_bridge.configure(state=tk.DISABLED)
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_stop.configure(state=tk.NORMAL)
        threading.Thread(target=self._run_bridge, args=(browser,), daemon=True).start()

    def _run_bridge(self, browser: str) -> None:
        """Worker: launch the browser, poll for auth cookies, save them."""
        driver = None
        try:
            from udemy_enroller.driver_manager import DriverManager

            self._append_log(f"Launching {browser} for login…\n", "info")
            try:
                dm = DriverManager(browser=browser, cloudflare_bypass=True)
            except Exception as exc:
                self._append_log(
                    f"Could not start {browser}: {exc}\n"
                    "Make sure that browser is installed.\n",
                    "error",
                )
                return

            driver = dm.driver
            driver.get("https://www.udemy.com/")
            self._append_log("Waiting for you to log in (up to 5 minutes)…\n", "info")

            cookies = self._poll_for_login_cookies(driver)
            self._handle_bridge_result(cookies)
        except Exception as exc:
            self._append_log(f"Bridge error: {exc}\n", "error")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
            self.after(0, self._bridge_finished)

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
            self._append_log("Login cancelled.\n", "warn")
            return
        if "access_token" not in cookies:
            self._append_log(
                "Timed out waiting for login. Click Bridge Cookies to retry.\n",
                "warn",
            )
            return

        missing = [
            c for c in ("access_token", "client_id", "csrftoken") if c not in cookies
        ]
        if missing:
            self._append_log(
                f"Almost — still missing {missing}. Make sure you are on the "
                "Udemy homepage, then try again.\n",
                "warn",
            )
            return

        os.makedirs(APP_DIR, exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            f.write(json.dumps(cookies))
        self._append_log("Saved your login — you're ready to enroll!\n", "success")

    def _bridge_finished(self) -> None:
        self._bridging = False
        self._btn_bridge.configure(state=tk.NORMAL)
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.DISABLED)
        self._refresh_status()

    # ── Enrollment ───────────────────────────────────────────────────────────

    def _build_flags(self) -> List[str]:
        """Build the CLI flag list from the current UI state (REST mode)."""
        flags: List[str] = []
        if self._var_discudemy.get():
            flags.append("--discudemy")
        if self._var_idc.get():
            flags.append("--idownloadcoupon")
        if self._var_fbg.get():
            flags.append("--freebiesglobal")
        if self._var_tutbar.get():
            flags.append("--tutorialbar")
        if self._var_cvania.get():
            flags.append("--coursevania")
        flags += ["--max-pages", str(self._var_pages.get())]
        if self._var_debug.get():
            flags.append("--debug")
        return flags

    def _start_enrollment(self) -> None:
        if self._process is not None or self._bridging:
            return

        # A valid cookie is required: without it the enroller would fall back to
        # an interactive email/password/OTP login, which can't work in a windowed
        # app (no console). Direct the user to log in first.
        if not _cookie_valid():
            messagebox.showinfo(
                "Log in first",
                "You need to log in before enrolling.\n\n"
                'Click "Bridge Cookies" above and sign in to Udemy — then the '
                "Setup Status will turn green and you can Start Enrollment.",
            )
            return

        try:
            self._save_filter_settings()
        except Exception as exc:
            self._log_write(f"Warning: could not save filter settings: {exc}\n", "warn")

        flags = self._build_flags()
        cmd = _find_enroller_cmd(flags)
        self._log_write(f"$ {' '.join(cmd)}\n\n", "dim")
        self._btn_start.configure(state=tk.DISABLED)
        self._btn_stop.configure(state=tk.NORMAL)
        self._stop_event.clear()

        threading.Thread(target=self._stream_enroller, args=(cmd,), daemon=True).start()

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
                self._append_log(
                    f"\nEnroller exited with code {code}. See {log_path}\n", "error"
                )
        except Exception as exc:
            self._append_log(f"Launcher error: {exc}\n", "error")
        finally:
            self._process = None
            self.after(0, self._enrollment_finished)

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
        """Append new lines written to *log_path* since *offset*; return new end."""
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                new_text = f.read()
                offset = f.tell()
        except OSError:
            return offset
        for line in new_text.splitlines(keepends=True):
            self._append_log(line)
        return offset

    def _enrollment_finished(self) -> None:
        self._btn_start.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.DISABLED)
        self._refresh_status()
        self._log_write("\n─── Run complete ───\n", "stats")

    def _stop_enrollment(self) -> None:
        self._stop_event.set()
        if self._process is not None:
            try:
                self._process.terminate()
            except Exception:
                pass

    # ── Log helpers ──────────────────────────────────────────────────────────

    def _tag_for_line(self, line: str) -> Optional[str]:
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

    def _append_log(self, line: str, tag: Optional[str] = None) -> None:
        resolved_tag = tag or self._tag_for_line(line)
        self.after(0, lambda: self._log_write(line, resolved_tag))

    def _log_write(self, text: str, tag: Optional[str] = None) -> None:
        self._log.configure(state=tk.NORMAL)
        if tag:
            self._log.insert(tk.END, text, tag)
        else:
            self._log.insert(tk.END, text)
        self._log.configure(state=tk.DISABLED)
        self._log.see(tk.END)

    def _clear_log(self) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)


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

    App().mainloop()


if __name__ == "__main__":
    main()
