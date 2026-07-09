#!/usr/bin/env python3
"""GUI launcher for Udemy Course Enroller."""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk

APP_VERSION = "1.2.0"
GITHUB_REPO = "moayadbah/udemy-free-course-enroller"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(os.path.expanduser("~"), ".udemy_enroller")
COOKIE_FILE = os.path.join(APP_DIR, ".cookie")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.yaml")
PREFS_FILE = os.path.join(APP_DIR, "gui_prefs.json")

_SYS = platform.system()

if _SYS == "Darwin":
    _MONO_FONT = "Menlo"
elif _SYS == "Windows":
    _MONO_FONT = "Consolas"
else:
    _MONO_FONT = "DejaVu Sans Mono"

# Log terminal colours (fixed dark, independent of light/dark app mode)
_LOG_BG = "#101418"
_LOG_FG = "#d4d4d4"

# (label shown in the dropdown, value passed to the driver manager)
# These browsers are used only for the interactive login/bridge step; the
# Cloudflare-bypass attach logic in driver_manager.py supports all of them.
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

# Log-line markers → progress counter keys (each marks one processed course)
_PROGRESS_MARKERS: List[Tuple[str, str]] = [
    ("Successfully enrolled:", "enrolled"),
    ("Already enrolled in:", "already"),
    ("language not wanted", "skipped"),
    ("does not have a wanted category", "skipped"),
    ("as it now costs", "expired"),
    ("as it is always FREE", "expired"),
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


def _load_prefs() -> Dict:
    """Load remembered GUI preferences; empty dict when missing/corrupt."""
    try:
        with open(PREFS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


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


class App(ctk.CTk):
    """Main application window."""

    def __init__(self):
        """Initialize."""
        prefs = _load_prefs()
        appearance = prefs.get("appearance", "Dark")
        ctk.set_appearance_mode(appearance.lower())
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.title("Udemy Course Enroller")
        self.geometry("1020x820")
        self.minsize(900, 700)
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._bridging = False
        self._progress_determinate = False
        self._prog: Dict = {}
        self._reset_progress()
        self._build_ui()
        self._apply_prefs(prefs)
        self._refresh_status()
        self._load_filter_settings()
        self._update_bridge_label()
        self._update_run_summary()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        threading.Thread(target=self._check_updates, daemon=True).start()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._init_fonts()
        self._build_header()

        ctk.CTkLabel(
            self,
            text=f"v{APP_VERSION}",
            font=self._font_hint,
            text_color=("gray55", "gray45"),
        ).pack(side="bottom", anchor="e", padx=20, pady=(0, 6))

        self._tabs = ctk.CTkTabview(
            self, corner_radius=10, command=self._update_run_summary
        )
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(4, 2))
        setup_tab = self._tabs.add("  Setup  ")
        run_tab = self._tabs.add("  Run  ")

        self._build_setup_tab(setup_tab)
        self._build_run_tab(run_tab)

    def _init_fonts(self) -> None:
        self._font_title = ctk.CTkFont(size=22, weight="bold")
        self._font_card_title = ctk.CTkFont(size=15, weight="bold")
        self._font_bold = ctk.CTkFont(size=13, weight="bold")
        self._font_body = ctk.CTkFont(size=12)
        self._font_hint = ctk.CTkFont(size=11)
        self._font_badge = ctk.CTkFont(size=12, weight="bold")
        self._font_button = ctk.CTkFont(size=14, weight="bold")
        self._font_mono = ctk.CTkFont(family=_MONO_FONT, size=12)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 4))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Udemy Course Enroller", font=self._font_title).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            left,
            text="Auto-enroll in free Udemy courses using coupon scrapers",
            font=self._font_hint,
            text_color=("gray40", "gray60"),
        ).pack(anchor="w")

        self._var_appearance = tk.StringVar(value="Dark")
        ctk.CTkSegmentedButton(
            header,
            values=["System", "Light", "Dark"],
            variable=self._var_appearance,
            command=self._set_appearance,
            font=self._font_hint,
            height=26,
        ).pack(side="right")

        # Shown by the update checker only when a newer release exists
        self._btn_update = ctk.CTkButton(
            header,
            text="Update available ↗",
            font=self._font_hint,
            height=26,
            width=150,
            fg_color=("#2e7d32", "#1b5e20"),
            hover_color=("#1b5e20", "#144a19"),
            command=lambda: webbrowser.open(RELEASES_URL),
        )

    def _set_appearance(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())
        self._persist_prefs()

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        """Create a rounded section card; return its content frame."""
        card = ctk.CTkFrame(parent, corner_radius=12)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(card, text=title, font=self._font_card_title).pack(
            anchor="w", padx=16, pady=(12, 0)
        )
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=(4, 14))
        return body

    def _ghost_button(self, parent, text: str, command) -> ctk.CTkButton:
        """Small bordered secondary button."""
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            font=self._font_hint,
            width=64,
            height=26,
            fg_color="transparent",
            border_width=1,
            border_color=("gray60", "gray40"),
            text_color=("gray25", "gray75"),
            hover_color=("gray85", "gray25"),
        )

    def _hint(self, parent, text: str, **pack_kw) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=self._font_hint,
            text_color=("gray40", "gray60"),
            justify="left",
            wraplength=780,
        ).pack(anchor="w", **pack_kw)

    # ── Setup tab ────────────────────────────────────────────────────────────

    def _build_setup_tab(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Ordered for a first-time user: explain the flow, then the one required
        # choice (browser), then optional tweaks, then the readiness check last.
        self._build_getting_started_section(scroll)
        self._build_browser_section(scroll)
        self._build_scraper_section(scroll)
        self._build_filter_section(scroll)
        self._build_status_section(scroll)

    def _build_getting_started_section(self, parent) -> None:
        body = self._card(parent, "Getting Started")
        ctk.CTkLabel(
            body,
            text="New here? Three steps to your first free courses:",
            font=self._font_bold,
        ).pack(anchor="w")

        self._add_step(
            body,
            1,
            "Pick your login browser",
            "Right below — choose whichever browser you have installed.",
        )
        self._add_step(
            body,
            2,
            "Log in to Udemy once",
            'Run tab → "Bridge Cookies". Enter your email, password, and the '
            "6-digit code Udemy emails you. This turns the status below green.",
        )
        self._add_step(
            body,
            3,
            "Start enrolling",
            'Run tab → "Start Enrollment", then watch the progress bar and log.',
        )

        self._hint(
            body,
            "Logged-in sessions last days — repeat step 2 only when needed.",
            pady=(10, 0),
        )

    def _add_step(self, parent, number: int, action: str, detail: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            row,
            text=str(number),
            width=26,
            height=26,
            corner_radius=13,
            fg_color=("#3B8ED0", "#1F6AA5"),
            text_color="white",
            font=self._font_badge,
        ).pack(side="left", padx=(0, 12), anchor="n")
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col, text=action, font=self._font_bold).pack(anchor="w")
        ctk.CTkLabel(
            col,
            text=detail,
            font=self._font_hint,
            text_color=("gray40", "gray60"),
            justify="left",
            wraplength=740,
        ).pack(anchor="w")

    def _build_browser_section(self, parent) -> None:
        body = self._card(parent, "Login Browser")
        self._hint(
            body,
            "Used by the Bridge Cookies step to log in past Cloudflare. "
            "Enrollment itself uses fast REST mode (no browser window).",
            pady=(0, 8),
        )
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Browser:", font=self._font_body).pack(side="left")
        browser_labels = [label for label, _ in BROWSER_OPTIONS]
        self._var_browser_label = tk.StringVar(value=browser_labels[0])
        ctk.CTkOptionMenu(
            row,
            values=browser_labels,
            variable=self._var_browser_label,
            command=self._on_browser_change,
            font=self._font_body,
            width=160,
            height=30,
        ).pack(side="left", padx=10)

    def _on_browser_change(self, *_) -> None:
        self._update_bridge_label()
        self._persist_prefs()

    def _build_scraper_section(self, parent) -> None:
        body = self._card(parent, "Scrapers")
        self._hint(body, "Coupon sites to scan for free-course codes.", pady=(0, 8))

        self._var_discudemy = tk.BooleanVar(value=True)
        self._var_idc = tk.BooleanVar(value=True)
        self._var_fbg = tk.BooleanVar(value=True)
        self._var_tutbar = tk.BooleanVar(value=False)
        self._var_cvania = tk.BooleanVar(value=False)

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x")
        scrapers = [
            ("discudemy", self._var_discudemy),
            ("idownloadcoupon", self._var_idc),
            ("freebiesglobal", self._var_fbg),
            ("tutorialbar  ⚠ offline", self._var_tutbar),
            ("coursevania  ⚠ JS-blocked", self._var_cvania),
        ]
        for i, (name, var) in enumerate(scrapers):
            ctk.CTkCheckBox(
                grid,
                text=name,
                variable=var,
                command=self._on_pref_change,
                font=self._font_body,
                checkbox_width=19,
                checkbox_height=19,
            ).grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 24), pady=4)

        opts = ctk.CTkFrame(body, fg_color="transparent")
        opts.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(opts, text="Max pages per scraper:", font=self._font_body).pack(
            side="left"
        )
        self._var_pages = tk.IntVar(value=5)
        self._slider_pages = ctk.CTkSlider(
            opts,
            from_=1,
            to=20,
            number_of_steps=19,
            width=220,
            command=self._on_pages_slide,
        )
        self._slider_pages.set(5)
        self._slider_pages.pack(side="left", padx=10)
        self._lbl_pages = ctk.CTkLabel(opts, text="5", font=self._font_bold, width=26)
        self._lbl_pages.pack(side="left")

        self._var_debug = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            opts,
            text="Debug logging",
            variable=self._var_debug,
            command=self._on_pref_change,
            font=self._font_body,
        ).pack(side="left", padx=(28, 0))

    def _on_pages_slide(self, value: float) -> None:
        pages = int(round(value))
        self._var_pages.set(pages)
        self._lbl_pages.configure(text=str(pages))

    def _on_pref_change(self, *_) -> None:
        self._persist_prefs()
        self._update_run_summary()

    def _build_filter_section(self, parent) -> None:
        body = self._card(parent, "Course Filters")
        self._hint(
            body,
            "Only enroll in courses that match your picks. "
            "Nothing selected = accept everything. Saved before each run.",
        )

        self._lang_vars: Dict[str, tk.BooleanVar] = {}
        self._var_lang_other = tk.StringVar()
        self._build_choice_group(
            body, "Languages", LANGUAGE_OPTIONS, self._lang_vars, self._var_lang_other
        )

        self._cat_vars: Dict[str, tk.BooleanVar] = {}
        self._var_cat_other = tk.StringVar()
        self._build_choice_group(
            body, "Categories", CATEGORY_OPTIONS, self._cat_vars, self._var_cat_other
        )

    def _build_choice_group(
        self,
        parent,
        title: str,
        options: List[str],
        vars_dict: Dict[str, tk.BooleanVar],
        other_var: tk.StringVar,
    ) -> None:
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", pady=(12, 4))
        ctk.CTkLabel(hdr, text=title, font=self._font_bold).pack(side="left")
        self._ghost_button(
            hdr, "Clear", lambda: self._clear_choices(vars_dict, other_var)
        ).pack(side="right")

        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.pack(fill="x")
        for i, name in enumerate(options):
            var = tk.BooleanVar(value=False)
            vars_dict[name] = var
            ctk.CTkCheckBox(
                grid,
                text=name,
                variable=var,
                command=self._update_run_summary,
                font=self._font_body,
                checkbox_width=19,
                checkbox_height=19,
            ).grid(row=i // 4, column=i % 4, sticky="w", padx=(0, 12), pady=4)
        for col in range(4):
            grid.columnconfigure(col, weight=1)

        other_row = ctk.CTkFrame(parent, fg_color="transparent")
        other_row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(other_row, text="Other:", font=self._font_body).pack(side="left")
        ctk.CTkEntry(other_row, textvariable=other_var, width=260, height=28).pack(
            side="left", padx=10
        )
        ctk.CTkLabel(
            other_row,
            text="anything not listed, comma-separated (optional)",
            font=self._font_hint,
            text_color=("gray45", "gray55"),
        ).pack(side="left")

    def _clear_choices(
        self, vars_dict: Dict[str, tk.BooleanVar], other_var: tk.StringVar
    ) -> None:
        for var in vars_dict.values():
            var.set(False)
        other_var.set("")
        self._update_run_summary()

    def _build_status_section(self, parent) -> None:
        body = self._card(parent, "Setup Status")

        r1 = ctk.CTkFrame(body, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        self._dot_settings = ctk.CTkLabel(
            r1, text="●", font=self._font_bold, text_color="gray", width=16
        )
        self._dot_settings.pack(side="left")
        self._lbl_settings = ctk.CTkLabel(r1, text="Checking…", font=self._font_body)
        self._lbl_settings.pack(side="left", padx=8)
        self._ghost_button(r1, "Refresh", self._refresh_status).pack(side="right")

        r2 = ctk.CTkFrame(body, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        self._dot_cookie = ctk.CTkLabel(
            r2, text="●", font=self._font_bold, text_color="gray", width=16
        )
        self._dot_cookie.pack(side="left")
        self._lbl_cookie = ctk.CTkLabel(r2, text="Checking…", font=self._font_body)
        self._lbl_cookie.pack(side="left", padx=8)
        self._btn_login_now = ctk.CTkButton(
            r2,
            text="Log in now →",
            command=self._go_login,
            font=self._font_hint,
            width=110,
            height=26,
        )

    def _go_login(self) -> None:
        """Jump to the Run tab and start the login (bridge) flow."""
        self._tabs.set("  Run  ")
        self._bridge_cookies()

    # ── Run tab ──────────────────────────────────────────────────────────────

    def _build_run_tab(self, parent) -> None:
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.pack(fill="x", pady=(4, 6))

        self._btn_bridge = ctk.CTkButton(
            actions,
            text="Bridge Cookies",
            command=self._bridge_cookies,
            font=self._font_body,
            height=38,
            fg_color="transparent",
            border_width=1,
            border_color=("gray55", "gray45"),
            text_color=("gray20", "gray85"),
            hover_color=("gray85", "gray25"),
        )
        self._btn_bridge.pack(side="left", padx=(0, 10))
        self._btn_start = ctk.CTkButton(
            actions,
            text="Start Enrollment",
            command=self._start_enrollment,
            font=self._font_button,
            height=38,
        )
        self._btn_start.pack(side="left", padx=(0, 10))
        self._btn_stop = ctk.CTkButton(
            actions,
            text="Stop",
            command=self._stop_enrollment,
            font=self._font_body,
            height=38,
            width=80,
            state="disabled",
            fg_color="#c62828",
            hover_color="#8e0000",
        )
        self._btn_stop.pack(side="left")

        self._progress_row = ctk.CTkFrame(parent, fg_color="transparent")
        self._progress = ctk.CTkProgressBar(self._progress_row, mode="indeterminate")
        self._progress.pack(side="left", fill="x", expand=True)
        self._lbl_progress = ctk.CTkLabel(
            self._progress_row, text="", font=self._font_hint
        )
        self._lbl_progress.pack(side="left", padx=(12, 0))

        self._lbl_summary = ctk.CTkLabel(
            parent,
            text="",
            font=self._font_hint,
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self._lbl_summary.pack(fill="x", pady=(2, 6))

        # End-of-run result banner (hidden until a run completes)
        self._result_card = ctk.CTkFrame(
            parent, corner_radius=10, fg_color=("#dcefdc", "#1e3320")
        )
        self._lbl_result = ctk.CTkLabel(
            self._result_card, text="", font=self._font_bold
        )
        self._lbl_result.pack(padx=14, pady=8, anchor="w")

        log_hdr = ctk.CTkFrame(parent, fg_color="transparent")
        log_hdr.pack(fill="x")
        ctk.CTkLabel(log_hdr, text="Log", font=self._font_card_title).pack(side="left")
        self._ghost_button(log_hdr, "Clear log", self._clear_log).pack(side="right")

        self._log = ctk.CTkTextbox(
            parent,
            corner_radius=10,
            fg_color=_LOG_BG,
            text_color=_LOG_FG,
            font=self._font_mono,
            wrap="word",
            state="disabled",
        )
        self._log.pack(fill="both", expand=True, pady=(6, 4))
        self._log.tag_config("error", foreground="#f48771")
        self._log.tag_config("success", foreground="#89d185")
        self._log.tag_config("info", foreground="#569cd6")
        self._log.tag_config("warn", foreground="#dcdcaa")
        self._log.tag_config("stats", foreground="#c586c0")
        self._log.tag_config("dim", foreground="#808080")

    def _set_busy(self, busy: bool) -> None:
        """Show/hide the progress row; starts in indeterminate (pulsing) mode."""
        if busy:
            self._result_card.pack_forget()
            self._progress_determinate = False
            self._progress.configure(mode="indeterminate")
            self._lbl_progress.configure(text="")
            self._progress_row.pack(fill="x", pady=(2, 2), after=self._btn_stop.master)
            self._progress.start()
        else:
            self._progress.stop()
            self._progress_row.pack_forget()

    # ── Progress tracking ────────────────────────────────────────────────────

    def _reset_progress(self) -> None:
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
        """Update counters from a fresh enroller log line."""
        p = self._prog
        if "Total courses this time:" in line:
            try:
                p["total"] += int(line.rsplit(":", 1)[1].strip())
            except ValueError:
                pass
            return
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

    def _update_progress_ui(self) -> None:
        p = self._prog
        if not p["total"]:
            return
        if not self._progress_determinate:
            self._progress_determinate = True
            self._progress.stop()
            self._progress.configure(mode="determinate")
        self._progress.set(min(1.0, p["processed"] / p["total"]))
        skipped = p["already"] + p["skipped"] + p["expired"]
        self._lbl_progress.configure(
            text=(
                f"Course {p['processed']} / {p['total']}   ·   "
                f"Enrolled {p['enrolled']}   ·   Skipped {skipped}"
            )
        )

    def _show_result_card(self) -> None:
        p = self._prog
        enrolled = (
            p["stats_enrolled"] if p["stats_enrolled"] is not None else p["enrolled"]
        )
        if p["total"] == 0 and enrolled == 0:
            return
        text = f"✓  Enrolled in {enrolled} new course{'s' if enrolled != 1 else ''}"
        if p["savings"]:
            text += f"  —  saved {p['savings']}"
        self._lbl_result.configure(text=text)
        self._result_card.pack(fill="x", pady=(0, 8), before=self._log)

    # ── Status ───────────────────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        """Re-check whether settings.yaml and the cookie file are present."""
        if _settings_exist():
            self._dot_settings.configure(text_color="#43a047")
            self._lbl_settings.configure(text="Settings saved")
        else:
            self._dot_settings.configure(text_color="gray")
            self._lbl_settings.configure(
                text="Settings: none yet — saved automatically on your first run"
            )

        if _cookie_valid():
            self._dot_cookie.configure(text_color="#43a047")
            self._lbl_cookie.configure(text="Logged in — ready to enroll")
            self._btn_login_now.pack_forget()
        else:
            self._dot_cookie.configure(text_color="#e53935")
            self._lbl_cookie.configure(text="Not logged in yet")
            self._btn_login_now.pack(side="right")

    # ── Preferences ──────────────────────────────────────────────────────────

    def _current_prefs(self) -> Dict:
        try:
            pages = int(self._var_pages.get())
        except tk.TclError:
            pages = 5
        return {
            "appearance": self._var_appearance.get(),
            "browser": self._var_browser_label.get(),
            "scrapers": {
                "discudemy": bool(self._var_discudemy.get()),
                "idownloadcoupon": bool(self._var_idc.get()),
                "freebiesglobal": bool(self._var_fbg.get()),
                "tutorialbar": bool(self._var_tutbar.get()),
                "coursevania": bool(self._var_cvania.get()),
            },
            "max_pages": pages,
            "debug": bool(self._var_debug.get()),
        }

    def _persist_prefs(self, *_) -> None:
        _save_prefs(self._current_prefs())

    def _apply_prefs(self, prefs: Dict) -> None:
        """Restore remembered choices; unknown/missing values keep defaults."""
        if not prefs:
            return
        self._var_appearance.set(prefs.get("appearance", "Dark"))
        browser = prefs.get("browser")
        if browser in [label for label, _ in BROWSER_OPTIONS]:
            self._var_browser_label.set(browser)
        scrapers = prefs.get("scrapers") or {}
        for key, var in (
            ("discudemy", self._var_discudemy),
            ("idownloadcoupon", self._var_idc),
            ("freebiesglobal", self._var_fbg),
            ("tutorialbar", self._var_tutbar),
            ("coursevania", self._var_cvania),
        ):
            if key in scrapers:
                var.set(bool(scrapers[key]))
        pages = prefs.get("max_pages")
        if isinstance(pages, int) and 1 <= pages <= 20:
            self._var_pages.set(pages)
            self._slider_pages.set(pages)
            self._lbl_pages.configure(text=str(pages))
        self._var_debug.set(bool(prefs.get("debug", False)))

    def _on_close(self) -> None:
        self._persist_prefs()
        self._stop_event.set()
        self.destroy()

    # ── Update checker ───────────────────────────────────────────────────────

    def _check_updates(self) -> None:
        """Quietly look for a newer GitHub release; show a button if found."""
        try:
            import requests

            resp = requests.get(LATEST_API, timeout=5)
            tag = resp.json().get("tag_name", "")
            if self._is_newer(tag, APP_VERSION):
                self.after(0, lambda: self._btn_update.pack(side="right", padx=(0, 10)))
        except Exception:
            pass

    @staticmethod
    def _is_newer(remote: str, local: str) -> bool:
        def parse(version: str) -> Tuple[int, ...]:
            parts = re.findall(r"\d+", version)[:3]
            return tuple(int(p) for p in parts) if parts else (0,)

        return parse(remote) > parse(local)

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
        """Populate the language/category checkboxes from settings.yaml."""
        data = _load_yaml()
        if data is None:
            return
        udemy = data.get("udemy") or {}
        self._apply_choices(
            udemy.get("languages") or [], self._lang_vars, self._var_lang_other
        )
        self._apply_choices(
            udemy.get("categories") or [], self._cat_vars, self._var_cat_other
        )

    def _apply_choices(
        self,
        saved: List[str],
        vars_dict: Dict[str, tk.BooleanVar],
        other_var: tk.StringVar,
    ) -> None:
        """Check the boxes matching *saved* values; overflow goes to Other."""
        lookup = {name.lower(): name for name in vars_dict}
        extras: List[str] = []
        for value in saved:
            text = str(value).strip()
            if not text:
                continue
            canonical = lookup.get(text.lower())
            if canonical:
                vars_dict[canonical].set(True)
            else:
                extras.append(text)
        other_var.set(", ".join(extras))

    def _collect_choices(
        self, vars_dict: Dict[str, tk.BooleanVar], other_var: tk.StringVar
    ) -> List[str]:
        """Return checked options plus any custom entries, deduplicated."""
        chosen = [name for name, var in vars_dict.items() if var.get()]
        # Accept the Arabic comma (،) as a separator too, not just the ASCII one.
        raw = other_var.get().strip().replace("،", ",")
        seen = {name.lower() for name in chosen}
        for item in raw.split(","):
            text = item.strip()
            if text and text.lower() not in seen:
                chosen.append(text)
                seen.add(text.lower())
        return chosen

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

        udemy["languages"] = self._collect_choices(
            self._lang_vars, self._var_lang_other
        )
        udemy["categories"] = self._collect_choices(self._cat_vars, self._var_cat_other)

        data["udemy"] = udemy
        _save_yaml(data)

    # ── Run summary ──────────────────────────────────────────────────────────

    def _update_run_summary(self, *_) -> None:
        """Refresh the one-line recap of what Start Enrollment will do."""
        scraper_vars = (
            self._var_discudemy,
            self._var_idc,
            self._var_fbg,
            self._var_tutbar,
            self._var_cvania,
        )
        count = sum(var.get() for var in scraper_vars)
        langs = self._summarize(self._lang_vars, self._var_lang_other)
        cats = self._summarize(self._cat_vars, self._var_cat_other)
        try:
            pages = self._var_pages.get()
        except tk.TclError:
            pages = "?"
        self._lbl_summary.configure(
            text=(
                f"Scrapers: {count}   ·   Max pages: {pages}   ·   "
                f"Languages: {langs}   ·   Categories: {cats}"
            )
        )

    def _summarize(
        self, vars_dict: Dict[str, tk.BooleanVar], other_var: tk.StringVar
    ) -> str:
        values = self._collect_choices(vars_dict, other_var)
        if not values:
            return "all"
        if len(values) > 3:
            return ", ".join(values[:3]) + f" +{len(values) - 3} more"
        return ", ".join(values)

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
        self._btn_bridge.configure(state="disabled")
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._set_busy(True)
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
        self._btn_bridge.configure(state="normal")
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._set_busy(False)
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
        self._persist_prefs()
        self._update_run_summary()
        self._reset_progress()

        flags = self._build_flags()
        cmd = _find_enroller_cmd(flags)
        self._log_write(f"$ {' '.join(cmd)}\n\n", "dim")
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._set_busy(True)
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
            self._parse_progress(line)
            self._append_log(line)
        if new_text:
            self.after(0, self._update_progress_ui)
        return offset

    def _enrollment_finished(self) -> None:
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._set_busy(False)
        self._refresh_status()
        self._show_result_card()
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
        self._log.configure(state="normal")
        if tag:
            self._log.insert("end", text, tag)
        else:
            self._log.insert("end", text)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")


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
