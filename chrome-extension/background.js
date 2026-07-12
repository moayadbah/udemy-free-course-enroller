/*
 * Service worker: scraping engine + enrollment orchestrator.
 *
 * Coupon sites are scraped here (cross-origin, allowed by host_permissions).
 * Every Udemy call is delegated to the udemy-agent content script so it runs
 * same-origin inside a www.udemy.com tab with the user's real session.
 */

const DEFAULT_PREFS = {
  theme: "dark",
  scrapers: {
    discudemy: true,
    idownloadcoupon: true,
    freebiesglobal: true,
  },
  max_pages: 3,
  filters: { languages: [], categories: [] },
};

const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36";

const COUPON_RE = /https:\/\/www\.udemy\.com\/course\/[^"'\s\\<>]+?\?couponCode=[A-Za-z0-9._%-]+/g;

let RUN = { running: false, stop: false };
let PROG = freshProgress();

function freshProgress() {
  return {
    total: 0,
    processed: 0,
    enrolled: 0,
    already: 0,
    skipped: 0,
    expired: 0,
    savings: 0,
    currency: "USD",
    courses: [],
  };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── UI messaging + state ────────────────────────────────────────────────────

function broadcast(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}
function log(text, tag) {
  broadcast({ type: "log", line: { text, tag: tag || null } });
}
function pushProgress() {
  broadcast({ type: "progress", data: PROG });
  chrome.storage.local.set({ runstate: { running: RUN.running, prog: PROG } });
}
async function getPrefs() {
  const { prefs } = await chrome.storage.local.get("prefs");
  return Object.assign(structuredClone(DEFAULT_PREFS), prefs || {});
}

// ── Udemy agent bridge ──────────────────────────────────────────────────────

async function findUdemyTab() {
  const tabs = await chrome.tabs.query({ url: "*://www.udemy.com/*" });
  return tabs.length ? tabs[0] : null;
}

async function pingTab(tabId) {
  try {
    const r = await chrome.tabs.sendMessage(tabId, { agent: true, op: "ping" });
    return !!(r && r.ok);
  } catch (e) {
    return false;
  }
}

// Chrome only auto-injects a manifest-declared content script into tabs that
// NAVIGATE after the extension is loaded. A Udemy tab the user already had
// open before installing/reloading the extension never gets it — so if a
// plain ping fails, inject it on demand instead of assuming "not logged in".
async function ensureAgentReady(tabId) {
  if (await pingTab(tabId)) return true;
  try {
    await chrome.scripting.executeScript({ target: { tabId }, files: ["udemy-agent.js"] });
  } catch (e) {
    return false; // e.g. tab navigated away or isn't a udemy.com page anymore
  }
  for (let i = 0; i < 10; i++) {
    if (await pingTab(tabId)) return true;
    await sleep(200);
  }
  return false;
}

async function ensureUdemyTab() {
  let tab = await findUdemyTab();
  if (!tab) {
    log("Opening a Udemy tab for your session…", "info");
    tab = await chrome.tabs.create({ url: "https://www.udemy.com/", active: false });
  }
  // Wait until the content script answers a ping (page + script ready),
  // injecting it manually if this tab predates the extension being loaded.
  for (let i = 0; i < 40; i++) {
    if (await ensureAgentReady(tab.id)) return tab.id;
    await sleep(500);
  }
  throw new Error("Could not reach the Udemy tab. Open www.udemy.com and retry.");
}

async function agent(tabId, op, args) {
  const resp = await chrome.tabs.sendMessage(tabId, { agent: true, op, args: args || {} });
  if (resp && resp.error) throw new Error(resp.error);
  return resp ? resp.result : null;
}

async function checkLoginStatus() {
  // Non-intrusive: only looks at a Udemy tab if one is already open, so just
  // viewing the app page never opens a new tab on its own.
  const tab = await findUdemyTab();
  if (!tab) return { logged_in: false };
  try {
    if (!(await ensureAgentReady(tab.id))) return { logged_in: false };
    const ctx = await agent(tab.id, "contextMe");
    return { logged_in: !!ctx.logged_in };
  } catch (e) {
    return { logged_in: false };
  }
}

// ── Coupon scrapers (regex-based; no DOM in a worker) ───────────────────────

async function fetchText(url) {
  const res = await fetch(url, { headers: { "User-Agent": BROWSER_UA } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.text();
}

function anchors(html) {
  // Return [{attrs, inner}] for every <a> tag.
  const out = [];
  const re = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(html))) out.push({ attrs: m[1], inner: m[2] });
  return out;
}
function attr(attrs, name) {
  const m = attrs.match(new RegExp(name + '=["\']([^"\']+)["\']', "i"));
  return m ? m[1] : null;
}
function couponUrls(html) {
  const found = new Set();
  let m;
  COUPON_RE.lastIndex = 0;
  while ((m = COUPON_RE.exec(html))) found.add(m[0].replace(/&amp;/g, "&"));
  return [...found];
}

async function mapLimit(items, limit, fn) {
  const out = [];
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) {
      const idx = i++;
      try {
        out.push(await fn(items[idx]));
      } catch (e) {
        /* skip this one */
      }
    }
  });
  await Promise.all(workers);
  return out.filter(Boolean);
}

async function scrapeDiscudemy(maxPages) {
  const links = [];
  for (let page = 1; page <= maxPages && !RUN.stop; page++) {
    let html;
    try {
      html = await fetchText(`https://discudemy.com/all/${page}`);
    } catch (e) {
      log(`discudemy page ${page}: ${e.message}`, "error");
      break;
    }
    const goPages = anchors(html)
      .filter((a) => /card-header/.test(a.attrs))
      .map((a) => attr(a.attrs, "href"))
      .filter(Boolean)
      .map((href) => `https://discudemy.com/go/${href.split("/").pop()}`);
    const found = await mapLimit(goPages, 5, async (go) => {
      const page = await fetchText(go);
      return couponUrls(page)[0] || null;
    });
    links.push(...found);
    log(`discudemy page ${page}: ${found.length} coupons`, "info");
  }
  return links;
}

async function scrapeFreebies(maxPages) {
  const links = [];
  for (let page = 1; page <= maxPages && !RUN.stop; page++) {
    let html;
    try {
      html = await fetchText(`https://freebiesglobal.com/tag/udemy/page/${page}/`);
    } catch (e) {
      log(`freebiesglobal page ${page}: ${e.message}`, "error");
      break;
    }
    const posts = [];
    const h2re = /<h2\b[^>]*>([\s\S]*?)<\/h2>/gi;
    let hm;
    while ((hm = h2re.exec(html))) {
      const a = anchors(hm[1])[0];
      const href = a && attr(a.attrs, "href");
      if (href && !/\/tag\//.test(href)) posts.push(href);
    }
    const found = await mapLimit(posts, 5, async (post) => {
      const page = await fetchText(post);
      return couponUrls(page)[0] || null;
    });
    links.push(...found);
    log(`freebiesglobal page ${page}: ${found.length} coupons`, "info");
  }
  return links;
}

function cleanUdemyUrl(url) {
  const decoded = decodeURIComponent(url);
  const path = decoded.match(/https:\/\/www\.udemy\.com(\/course\/[^/?\s]+)/);
  const code = decoded.match(/couponCode=([A-Za-z0-9]+)/);
  if (path && code) {
    return `https://www.udemy.com${path[1]}/?couponCode=${code[1]}`;
  }
  return null;
}

async function scrapeIdc(maxPages) {
  const links = [];
  for (let page = 1; page <= maxPages && !RUN.stop; page++) {
    let html;
    try {
      html = await fetchText(`https://www.idownloadcoupon.com/page/${page}/`);
    } catch (e) {
      log(`idownloadcoupon page ${page}: ${e.message}`, "error");
      break;
    }
    // Each product's 2nd anchor is the internal /udemy/<id>/ redirect link.
    const products = [];
    const liRe = /<li[^>]*class="[^"]*\bproduct\b[^"]*"[^>]*>([\s\S]*?)<\/li>/gi;
    let lm;
    while ((lm = liRe.exec(html))) {
      const as = anchors(lm[1]);
      const href = as[1] && attr(as[1].attrs, "href");
      if (href) products.push(href);
    }
    const found = await mapLimit(products, 5, async (link) => {
      const res = await fetch(link, { headers: { "User-Agent": BROWSER_UA } });
      return cleanUdemyUrl(res.url);
    });
    links.push(...found.filter(Boolean));
    log(`idownloadcoupon page ${page}: ${found.length} coupons`, "info");
  }
  return links;
}

// ── Enrollment run ──────────────────────────────────────────────────────────

function wantMatch(list, ...values) {
  if (!list.length) return true;
  const wanted = list.map((s) => s.toLowerCase());
  return values.some((v) => v && wanted.includes(String(v).toLowerCase()));
}

async function startRun() {
  if (RUN.running) return { error: "busy" };
  RUN = { running: true, stop: false };
  PROG = freshProgress();
  pushProgress();

  let tabId;
  try {
    tabId = await ensureUdemyTab();
  } catch (e) {
    log(e.message, "error");
    return finishRun();
  }

  // Confirm the user is logged in to Udemy in this browser.
  let ctx;
  try {
    ctx = await agent(tabId, "contextMe");
  } catch (e) {
    log("Could not read Udemy session: " + e.message, "error");
    return finishRun();
  }
  if (!ctx.logged_in) {
    log("You're not logged in to Udemy in this browser.", "error");
    broadcast({ type: "login", logged_in: false });
    return finishRun();
  }
  PROG.currency = ctx.currency;
  broadcast({ type: "login", logged_in: true });

  const prefs = await getPrefs();
  log("Loading your existing courses…", "info");
  let owned = new Set();
  try {
    owned = new Set(await agent(tabId, "subscribedCourseIds"));
    log(`You already own ${owned.size} courses.`, "info");
  } catch (e) {
    log("Could not load your course list (continuing).", "warn");
  }

  // Scrape coupon sites.
  log("Searching coupon sites…", "info");
  const jobs = [];
  if (prefs.scrapers.discudemy) jobs.push(scrapeDiscudemy(prefs.max_pages));
  if (prefs.scrapers.idownloadcoupon) jobs.push(scrapeIdc(prefs.max_pages));
  if (prefs.scrapers.freebiesglobal) jobs.push(scrapeFreebies(prefs.max_pages));
  const scraped = (await Promise.all(jobs)).flat();
  const couponLinks = [...new Set(scraped)];
  PROG.total = couponLinks.length;
  pushProgress();
  log(`Found ${couponLinks.length} coupons. Enrolling…`, "stats");

  const langs = prefs.filters.languages || [];
  const cats = prefs.filters.categories || [];

  for (const link of couponLinks) {
    if (RUN.stop) break;
    await sleep(1000 + Math.random() * 1000); // pace to dodge 403s
    try {
      await enrollOne(tabId, link, owned, langs, cats);
    } catch (e) {
      log(`Error on ${link}: ${e.message}`, "error");
    }
    PROG.processed++;
    pushProgress();
  }

  log("─── Run complete ───", "stats");
  notifyDone();
  return finishRun();
}

async function enrollOne(tabId, link, owned, langs, cats) {
  const url = link.split("?couponCode=")[0];
  const code = link.split("?couponCode=")[1];

  let idRes = await agent(tabId, "getCourseId", { url });
  for (let attempt = 0; attempt < 4 && idRes.status === 403; attempt++) {
    const wait = 5000 * 2 ** attempt;
    log(`Rate-limited (403); waiting ${wait / 1000}s…`, "warn");
    await sleep(wait);
    idRes = await agent(tabId, "getCourseId", { url });
  }
  if (!idRes.id) {
    log(`Couldn't read course id: ${url}`, "warn");
    return;
  }
  const id = idRes.id;

  if (owned.has(id)) {
    PROG.already++;
    return;
  }

  const details = await agent(tabId, "courseDetails", { id });
  if (!details) {
    log(`No details for course ${id}`, "warn");
    return;
  }
  const title = details.title || url;

  if (langs.length) {
    const loc = details.locale && details.locale.simple_english_title;
    if (!wantMatch(langs, loc)) {
      PROG.skipped++;
      log(`Skipped (language): ${title}`, "warn");
      return;
    }
  }
  if (cats.length) {
    const cat = details.primary_category && details.primary_category.title;
    const sub = details.primary_subcategory && details.primary_subcategory.title;
    if (!wantMatch(cats, cat, sub)) {
      PROG.skipped++;
      log(`Skipped (category): ${title}`, "warn");
      return;
    }
  }

  const coupon = await agent(tabId, "couponValid", { id, code });
  if (!coupon.valid) {
    PROG.expired++;
    log(`Expired/invalid coupon: ${title}`, "warn");
    return;
  }

  const result = await agent(tabId, "checkout", { id, code, currency: PROG.currency });
  if (result.status === "rate_limited") {
    await sleep(60000);
    const retry = await agent(tabId, "checkout", { id, code, currency: PROG.currency });
    if (retry.status !== "succeeded") {
      PROG.expired++;
      return;
    }
  } else if (result.status !== "succeeded") {
    PROG.expired++;
    log(`Checkout failed: ${title}`, "warn");
    return;
  }
  PROG.enrolled++;
  PROG.savings += coupon.savings || 0;
  PROG.courses.push({ title, url });
  broadcast({ type: "course", data: { title, url } });
  log(`Enrolled: ${title}`, "success");
}

function finishRun() {
  RUN.running = false;
  RUN.stop = false;
  broadcast({ type: "run_state", running: false });
  pushProgress();
  return { ok: true };
}

function notifyDone() {
  const saved = PROG.savings
    ? ` — saved ${PROG.currency} ${PROG.savings.toFixed(2)}`
    : "";
  try {
    chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "Run complete",
      message: `Enrolled in ${PROG.enrolled} new course${
        PROG.enrolled === 1 ? "" : "s"
      }${saved}`,
    });
  } catch (e) {
    /* notifications optional */
  }
}

// ── Message + lifecycle wiring ──────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.ui) return false;
  (async () => {
    if (msg.op === "getState") {
      sendResponse({
        running: RUN.running,
        prog: PROG,
        prefs: await getPrefs(),
      });
    } else if (msg.op === "start") {
      broadcast({ type: "run_state", running: true });
      startRun();
      sendResponse({ ok: true });
    } else if (msg.op === "stop") {
      RUN.stop = true;
      log("Stopping…", "warn");
      sendResponse({ ok: true });
    } else if (msg.op === "savePrefs") {
      await chrome.storage.local.set({ prefs: msg.prefs });
      sendResponse({ ok: true });
    } else if (msg.op === "openUrl") {
      chrome.tabs.create({ url: msg.url });
      sendResponse({ ok: true });
    } else if (msg.op === "checkLogin") {
      sendResponse(await checkLoginStatus());
    } else {
      sendResponse({ error: "unknown_op" });
    }
  })();
  return true;
});

// Any Udemy tab that was already open before this extension was loaded never
// received the manifest-declared content script (Chrome only auto-injects on
// navigations that happen after load). Inject it immediately on install/
// reload/browser-restart so login is detected right away, with no need for
// the user to refresh their existing tab.
async function injectIntoExistingUdemyTabs() {
  try {
    const tabs = await chrome.tabs.query({ url: "*://www.udemy.com/*" });
    for (const tab of tabs) {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["udemy-agent.js"],
        });
      } catch (e) {
        /* tab may have navigated away or be otherwise inaccessible */
      }
    }
  } catch (e) {
    /* ignore */
  }
}
chrome.runtime.onInstalled.addListener(injectIntoExistingUdemyTabs);
chrome.runtime.onStartup.addListener(injectIntoExistingUdemyTabs);

// Toolbar icon opens the full app page (focus if already open).
chrome.action.onClicked.addListener(async () => {
  const url = chrome.runtime.getURL("app.html");
  const existing = await chrome.tabs.query({ url });
  if (existing.length) {
    chrome.tabs.update(existing[0].id, { active: true });
    chrome.windows.update(existing[0].windowId, { focused: true });
  } else {
    chrome.tabs.create({ url });
  }
});

// Keep the worker alive while the app page is open: the page holds a port and
// pings it periodically, and that message traffic resets the idle timer. This
// is more reliable than alarms for long enrollment runs.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "keepalive") {
    port.onMessage.addListener(() => {}); // activity keeps the worker warm
    port.onDisconnect.addListener(() => {});
  }
});

// Backstop keepalive via alarm (fires even if no page is open).
chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => {
  if (RUN.running) chrome.runtime.getPlatformInfo(() => {});
});
