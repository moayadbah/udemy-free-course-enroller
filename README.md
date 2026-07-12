# Udemy Course Enroller — Free Courses, Automatically

Scrapes coupon links from several coupon aggregator sites and uses Udemy's REST API
to enroll you in those courses for free — no clicking, no copy-pasting.

> **NOT affiliated with Udemy. For educational / personal use only.
> Make sure web-scraping is legal in your region.**

---

## Download

[![Download for Windows](https://img.shields.io/badge/Download-Windows%20(.exe)-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/moayadbah/udemy-free-course-enroller/releases/latest/download/UdemyCourseEnroller.exe)
&nbsp;&nbsp;
[![Download for macOS](https://img.shields.io/badge/Download-macOS%20(.dmg)-000000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/moayadbah/udemy-free-course-enroller/releases/latest/download/UdemyCourseEnroller.dmg)

> Needs a Chromium browser (Brave/Chrome/Edge/Chromium) installed for the one-time login.
> The downloads are **unsigned**, so your OS warns you on first launch — see
> [Opening the app](#opening-the-app-first-launch) just below.

Prefer to run from source instead? See [Quick Start](#quick-start) below.

---

## Opening the app (first launch)

Both downloads are **unsigned** (no paid Apple/Microsoft signing certificate), so your operating
system will warn you the **first time** you open it. This is normal for indie/open-source apps and
does **not** mean anything is wrong with the download — here's how to get past it.

### macOS

You'll see *"UdemyCourseEnroller cannot be opened because it is from an unidentified developer"*
(or *"Apple could not verify it is free of malware"*). Use whichever works for your macOS version:

1. **Right-click → Open (easiest).** In Finder, **Control-click** the app — or click it with
   **two fingers** on the trackpad / right-click — then choose **Open**, and click **Open** again
   in the dialog. macOS remembers your choice, so after this you can just double-click it.
2. **Open Anyway (newer macOS, if step 1 shows no Open button).** Try to open it once (it gets
   blocked), then go to  **System Settings → Privacy & Security**, scroll to the bottom, and next
   to *"UdemyCourseEnroller was blocked…"* click **Open Anyway**, then confirm with your
   password / Touch ID.
3. **Terminal (power users).** Remove the quarantine flag, then open normally:
   ```
   xattr -dr com.apple.quarantine /Applications/UdemyCourseEnroller.app
   ```

> Tip: drag the app into your **Applications** folder first, then open it from there.

### Windows

SmartScreen shows *"Windows protected your PC"*. Click **More info**, then **Run anyway**.

If you'd rather avoid these warnings entirely, run from source instead (see
[Quick Start](#quick-start)).

---

## Quick Start

Udemy now requires Cloudflare verification and email 2FA on every login, so the
enroller can no longer log in by itself.  The workaround is a two-step "bridge":
you log in once through a real browser window (Brave, Chrome, Edge or Chromium),
then the enroller reuses those auth cookies for all future runs (until they expire —
usually days to weeks).

```
# Step 1 — only needed when cookies expire (default browser: brave)
python3 bridge_cookies.py
# ...or pick a browser: python3 bridge_cookies.py chrome

# Step 2 — enroll in all available free courses
udemy_enroller
```

Or launch the GUI (no terminal commands needed after setup):

```
python3 gui.py
```

---

## Requirements

- **Python 3.8+** (tested on 3.14; asyncio fix included)
- **A Chromium-based browser** — Brave, Chrome, Edge or Chromium — used for the
  cookie-bridge login step only. The default install location for each is detected
  automatically per OS (see `BROWSER_BINARIES` in `udemy_enroller/driver_manager.py`);
  edit that map if yours is installed somewhere non-standard.
- Python packages:

```
pip install -r requirements.txt
```

Or install the package itself (gives you the `udemy_enroller` command):

```
pip install .
```

---

## GUI

`gui.py` provides a modern desktop app: the interface is a web UI (HTML/CSS/JS in
`web/index.html`) rendered in your OS's native engine via
[pywebview](https://pywebview.flowrl.com) — smooth scrolling, dark/light themes,
and full Arabic (RTL) support.

```
pip install pywebview
python3 gui.py
```

Four pages in a sidebar:

| Page | What it does |
|---|---|
| **Home** | Login status, one big *Start Enrolling* button, live progress ("Course 12 of 43 · Enrolled 8 · Skipped 3"), end-of-run savings summary, and clickable links to every course you just enrolled in |
| **Filters** | Tap language and category chips to only enroll in what you want — nothing selected = accept everything |
| **Activity** | Full colour-coded live log |
| **Settings** | Login browser (auto-detects what's installed), interface language (English/العربية), theme, automatic scheduled runs, and Advanced options (coupon sources, max pages, debug) |

First launch shows a short guided setup. The app remembers all your choices,
sends a desktop notification when a run finishes, can re-run itself automatically
every few hours while open, and checks GitHub for newer releases on startup.

> **Windows note:** the interface uses Microsoft Edge WebView2, which is
> preinstalled on Windows 11 and virtually all updated Windows 10 systems. If the
> app window comes up empty, install the
> [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/).

---

## Standalone App (Windows `.exe` / macOS)

You can run the GUI as a single self-contained file — no Python install needed on the
machine that runs it. **A Chromium browser (Brave/Chrome/Edge/Chromium) is still
required** for the one-time login.

**Easiest — use the download buttons** at the top of this README: `UdemyCourseEnroller.exe`
for Windows and `UdemyCourseEnroller.dmg` for macOS. They point at the latest GitHub
**Release**, which is built and published automatically when a `v*` tag is pushed.

> The downloads are unsigned, so your OS warns you on first launch — see
> [Opening the app](#opening-the-app-first-launch) for the exact steps on macOS and Windows.

**Build it yourself:**

```
pip install -r requirements-build.txt
pyinstaller udemy_enroller_gui.spec
# Windows -> dist/UdemyCourseEnroller.exe
# macOS   -> dist/UdemyCourseEnroller.app  (wrap into a .dmg to share)
```

A `.exe` can only be built on Windows and a macOS app only on macOS — PyInstaller does not
cross-compile, which is why the [build workflow](.github/workflows/build-gui.yml) builds each
on its own runner.

---

## Chrome Extension (alternative to the desktop app)

There's also a **[Chrome extension](chrome-extension/)** version. It runs inside your own
browser where you're already signed in to Udemy, so there's no separate login step, no
Cloudflare/2FA bridge, and nothing to download or unblock — the browser handles everything.
See [chrome-extension/README.md](chrome-extension/README.md) for install steps (currently a
"Load unpacked" install — no Chrome Web Store listing yet).

---

## Bridge Cookies (First-time / Cookie Expired)

When your auth cookie is missing or expired, run (browser is optional, default `brave`):

```
python3 bridge_cookies.py            # uses Brave
python3 bridge_cookies.py chrome     # or chrome / edge / chromium
```

What happens:
1. The chosen browser launches with a clean temporary profile (no automation flags,
   so Cloudflare passes without intervention)
2. You are prompted to log in: enter your email, password, and the 6-digit OTP that
   Udemy emails you
3. Once your Udemy homepage is visible, press **Enter** in the terminal
4. The script extracts `access_token`, `client_id`, and `csrftoken` from the browser
   and saves them to `~/.udemy_enroller/.cookie`
5. You can now run `udemy_enroller` (or the GUI) — the REST enrollment loop reuses
   these cookies without opening a browser

---

## Scrapers

| Site | Status | Notes |
|---|---|---|
| [discudemy.com](https://discudemy.com) | ✅ Working | Default ON |
| [idownloadcoupon.com](https://idownloadcoupon.com) | ✅ Working | Default ON — link format changed to `/udemy/<id>/` redirects; handled automatically |
| [freebiesglobal.com](https://freebiesglobal.com) | ✅ Working | Default ON — listing URL moved to `/tag/udemy/page/N/`; handled automatically |
| [tutorialbar.com](https://tutorialbar.com) | ❌ Offline | Site has an invalid SSL cert; disabled by default |
| [coursevania.com](https://coursevania.com) | ❌ JS-blocked | Udemy link is now loaded via JavaScript / cookie redirect, not scrapable statically; disabled by default |

Dead scrapers can still be enabled explicitly (`--tutorialbar`, `--coursevania`) if the
sites ever come back online.

---

## CLI Usage

```
udemy_enroller [options]
```

| Flag | Default | Description |
|---|---|---|
| `--discudemy` | on | Enable discudemy scraper |
| `--idownloadcoupon` | on | Enable idownloadcoupon scraper |
| `--freebiesglobal` | on | Enable freebiesglobal scraper |
| `--tutorialbar` | off | Enable tutorialbar scraper (currently offline) |
| `--coursevania` | off | Enable coursevania scraper (JS-blocked) |
| `--browser BROWSER` | — | Control a browser directly instead of using REST cookies. Accepted values: `chrome`, `google-chrome`, `chromium`, `brave`, `edge` |
| `--max-pages N` | 5 | Max pages to scrape per site |
| `--delete-settings` | — | Delete saved settings file and re-prompt |
| `--delete-cookie` | — | Delete saved cookie file |
| `--debug` | — | Enable verbose debug logging |
| `--help` | — | Show full argument list |

When no scraper flags are passed, discudemy + idownloadcoupon + freebiesglobal are
enabled automatically (the three that currently work).

---

## Settings & Data Files

All user data lives in **`~/.udemy_enroller/`** — outside the project folder, so the
project directory is safe to share or version-control.

| File | Contents |
|---|---|
| `settings.yaml` | Udemy email, password, zip code, language/category filters |
| `.cookie` | Udemy auth cookies (access_token, client_id, csrftoken + session cookies) |
| `app.log` | Enrollment run history |

The first time you run `udemy_enroller` (or `bridge_cookies.py`) without a
`settings.yaml`, the CLI will prompt you to enter your credentials and optionally
save them.

---

## Run Statistics

At the end of each run a summary table is printed:

```
================== Run Statistics ==================

Enrolled:                   47
Unwanted Category:           0
Unwanted Language:           0
Already Claimed:            83
Expired:                    12
Total Enrolments:         1705
Savings:                $1030.53
================== Run Statistics ==================
```

---

## FAQs

**Can I get a specific course for free?**
No — the enroller only finds courses where the instructor has published a coupon link.
If you run it often enough, you will eventually pick up many courses you want.

**How often should I run it?**
Daily is ideal. Coupons expire quickly (often within 24–48 hours), so fresh runs
catch the most courses.

**Why does it need a browser at all?**
Udemy now uses Cloudflare Turnstile to block automated browsers.
A Selenium-controlled browser sets `navigator.webdriver = true`, which Cloudflare
detects and blocks. The fix is to launch the browser as a normal process (no
automation flags) and attach to it via Chrome DevTools Protocol — so Cloudflare sees
a real browser. You only need a browser for the one-time (or occasional) cookie-bridge
step; the daily enrollment runs use only REST API calls.

**Which browsers are supported for login?**
Any Chromium-based browser: **Brave, Chrome, Edge or Chromium**. Pick one in the GUI's
*Login Browser* dropdown, or pass it to `bridge_cookies.py` (e.g. `chrome`). The
Cloudflare-bypass attach in `driver_manager.py` works the same way for all of them; if
yours is installed in a non-standard location, edit the `BROWSER_BINARIES` map there.

**The enroller says "Exception in redeem courses: 'access_token'"**
Your cookie file is missing or expired. Run `python3 bridge_cookies.py` to refresh it.

---

## Docker

Build and run with Docker (useful for scheduled automation on a server, though the
cookie-bridge step still requires a local desktop browser):

```
docker build -t udemy_enroller .
docker run -it udemy_enroller
```

Mount a pre-built settings file:

```
docker run -v $(pwd)/settings.yaml:/home/enroller/.udemy_enroller/settings.yaml udemy_enroller
```

---

## Credits

This is a GUI edition built on top of the original
**[Automatic-Udemy-Course-Enroller](https://github.com/aapatre/Automatic-Udemy-Course-Enroller-GET-PAID-UDEMY-COURSES-for-FREE)**
by aapatre and contributors. All the original scraping/enrollment work is theirs; this fork
adds a desktop GUI, a browser-based login bridge (for Udemy's Cloudflare + 2FA), scraper
fixes, and single-file packaging.

## License

Licensed under **GPL-3.0**, the same license as the original project — see [LICENSE](LICENSE).
