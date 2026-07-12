# Udemy Free Course Enroller — Chrome Extension

A browser-native version of the desktop app. Because it runs **inside your own
browser where you're already signed in to Udemy**, there's no separate login,
no Cloudflare/2FA bridge, no packaging, and no DNS issues — the browser handles
everything.

> Not affiliated with Udemy. For enrolling in courses whose coupons are already
> free. Use responsibly and at your own discretion.

## Install (developer / unpacked)

1. Open **Google Chrome, Edge, or Brave** and make sure you're **logged in to
   [udemy.com](https://www.udemy.com/)**.
2. Go to `chrome://extensions` (or `edge://extensions`).
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** and select this `chrome-extension` folder.
5. Click the extension's icon in the toolbar — the full app opens in a tab.

## Use

- **Filters** — tap language/category chips to only enroll in what you want
  (nothing selected = accept everything).
- **Start Enrolling** — it searches the coupon sites, then enrolls you in each
  live 100%-off course, showing live progress and links to every course added.
- **Advanced** — pick which coupon sources to scan and how many pages each.

## How it works

- A content script on `www.udemy.com` performs every Udemy API/checkout call
  **same-origin**, using your real session cookies and CSRF token — exactly like
  clicking "Enroll" on the site yourself.
- The background service worker scrapes the coupon sites (discudemy,
  idownloadcoupon, freebiesglobal) and drives the enrollment loop, pacing
  requests to avoid Udemy's rate limits.

## Notes / limitations

- Keep the app tab open during a run (it keeps the background worker alive).
- Some coupon sites sit behind Cloudflare; if one returns nothing, the others
  still run.
- `idownloadcoupon` links redirect through third-party affiliate trackers before
  reaching Udemy. If a redirect hop lands on a domain outside this extension's
  permissions, that one coupon link is skipped (logged, not a crash). If you
  see this happening a lot, add the tracker domain to `host_permissions` in
  `manifest.json` and reload the extension.
- This is the "load unpacked" build. A one-click Chrome Web Store listing can be
  added later.
