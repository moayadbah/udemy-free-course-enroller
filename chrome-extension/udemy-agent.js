/*
 * Content script injected into www.udemy.com.
 *
 * Every Udemy API/checkout call is made from HERE so it is genuinely
 * same-origin: the browser attaches the user's real session cookies and we
 * pass the csrftoken as X-CSRFToken exactly like the Udemy website does. This
 * is what lets the extension skip the whole Selenium/Cloudflare/2FA login
 * bridge the desktop app needs.
 */

const API = "https://www.udemy.com";

function csrfToken() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : "";
}

async function apiGet(path) {
  const res = await fetch(API + path, {
    credentials: "same-origin",
    headers: { Accept: "application/json, text/plain, */*" },
  });
  return res;
}

// ── Individual operations ──────────────────────────────────────────────────

async function contextMe() {
  let currency = "USD";
  let logged = false;
  try {
    const res = await apiGet("/api-2.0/contexts/me/?me=True&Config=True");
    const data = await res.json();
    try {
      currency = data.Config.price_country.currency || "USD";
    } catch (e) {
      /* keep default */
    }
    if (data && data.header && typeof data.header.isLoggedIn === "boolean") {
      logged = data.header.isLoggedIn;
    }
  } catch (e) {
    /* fall through to the definitive check below */
  }
  // Definitive auth check: /users/me/ needs a real session.
  if (!logged) {
    try {
      const r = await apiGet("/api-2.0/users/me/?fields[user]=id");
      if (r.ok) {
        const u = await r.json();
        logged = !!(u && u.id);
      }
    } catch (e) {
      /* leave logged = false */
    }
  }
  return { logged_in: logged, currency };
}

async function subscribedCourseIds() {
  // Page through the user's owned courses to know what to skip.
  const ids = [];
  let url = "/api-2.0/users/me/subscribed-courses/?fields[course]=id&page_size=100";
  for (let guard = 0; guard < 60 && url; guard++) {
    const res = await apiGet(url);
    if (!res.ok) break;
    const data = await res.json();
    for (const c of data.results || []) ids.push(c.id);
    if (!data.next) break;
    url = data.next.replace(API, "");
  }
  return ids;
}

async function getCourseId(courseUrl) {
  const res = await fetch(courseUrl, { credentials: "same-origin" });
  if (res.status === 403) return { status: 403 };
  const html = await res.text();
  const m = html.match(/courseId=(\d+)/);
  if (m) return { id: parseInt(m[1], 10) };
  const m2 = html.match(/data-clp-course-id=["'](\d+)["']/);
  if (m2) return { id: parseInt(m2[1], 10) };
  return { id: null };
}

async function courseDetails(id) {
  const fields =
    "title,primary_category,primary_subcategory,locale";
  const res = await apiGet(
    `/api-2.0/courses/${id}/?fields[course]=${encodeURIComponent(fields)}`
  );
  if (!res.ok) return null;
  return await res.json();
}

async function couponValid(id, code) {
  const res = await apiGet(
    `/api-2.0/course-landing-components/${id}/me/?couponCode=${encodeURIComponent(
      code
    )}&components=price_text`
  );
  if (!res.ok) return { valid: false };
  const data = await res.json();
  try {
    const pricing = data.price_text.data.pricing_result;
    const price = pricing.price.amount;
    const listPrice = pricing.list_price.amount;
    if (price) return { valid: false, reason: "now costs" };
    if (!listPrice) return { valid: false, reason: "always free" };
    let savings = 0;
    try {
      savings = pricing.saving_price.amount || 0;
    } catch (e) {
      /* ignore */
    }
    return { valid: true, savings };
  } catch (e) {
    return { valid: false, reason: "no pricing" };
  }
}

async function checkout(id, code, currency) {
  const payload = {
    checkout_event: "Submit",
    checkout_environment: "Marketplace",
    shopping_info: {
      items: [
        {
          discountInfo: { code },
          buyable: { type: "course", id },
          price: { amount: 0, currency: currency || "USD" },
        },
      ],
      is_cart: false,
    },
    payment_info: {
      method_id: "0",
      payment_vendor: "Free",
      payment_method: "free-method",
    },
  };
  const res = await fetch(API + "/payment/checkout-submit/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(payload),
  });
  if (res.status === 429) {
    return { status: "rate_limited" };
  }
  if (!res.ok) return { status: "failed", code: res.status };
  const data = await res.json();
  return { status: data.status || "failed" };
}

// ── Message dispatch ────────────────────────────────────────────────────────

const HANDLERS = {
  ping: async () => ({ ok: true }),
  contextMe,
  subscribedCourseIds,
  getCourseId: (a) => getCourseId(a.url),
  courseDetails: (a) => courseDetails(a.id),
  couponValid: (a) => couponValid(a.id, a.code),
  checkout: (a) => checkout(a.id, a.code, a.currency),
};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.agent) return false;
  const handler = HANDLERS[msg.op];
  if (!handler) {
    sendResponse({ error: "unknown_op" });
    return false;
  }
  Promise.resolve(handler(msg.args || {}))
    .then((result) => sendResponse({ result }))
    .catch((e) => sendResponse({ error: String(e) }));
  return true; // async response
});
