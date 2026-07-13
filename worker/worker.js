/**
 * worker.js — Cloudflare Worker: instant Telegram webhook handler.
 * Handles /start, language selection, interest selection, /news, /help.
 * Reads/writes user prefs directly to Google Sheets.
 * For actual news content, triggers a GitHub Actions workflow_dispatch
 * (fast, one-off — not a slow cron poll) which does the heavy AI/RSS work
 * and sends the digest to the user.
 *
 * Required Worker secrets (set via wrangler secret put):
 *   TELEGRAM_BOT_TOKEN
 *   GOOGLE_CREDENTIALS_JSON   (raw service account JSON string)
 *   GOOGLE_SHEET_ID
 *   GH_PAT_FOR_WORKER         (GitHub PAT with repo+workflow scope)
 *   WEBHOOK_SECRET            (random string, verified against Telegram header)
 */

const GITHUB_REPO = "taraa-lab/design-news-bot";
const SHEET_NAME = "users";

const INTERESTS_FA = {
  automotive: "🚗 طراحی خودرو",
  product:    "📦 طراحی محصول",
  furniture:  "🛋️ طراحی مبلمان",
  jewelry:    "💍 طراحی جواهرات",
  accessory:  "👜 طراحی اکسسوری",
  service:    "🔧 طراحی خدمات",
};
const INTERESTS_EN = {
  automotive: "🚗 Automotive Design",
  product:    "📦 Product Design",
  furniture:  "🛋️ Furniture Design",
  jewelry:    "💍 Jewelry Design",
  accessory:  "👜 Accessory Design",
  service:    "🔧 Service Design",
};

const TEXTS = {
  fa: {
    welcome: "سلام! 👋 زبان مورد نظرت را انتخاب کن:",
    choose_int: "حوزه‌های علاقه‌مندیت را انتخاب کن (چند تا هم می‌شه):",
    done_btn: "✅ تأیید و دریافت اخبار",
    no_interest: "⚠️ حداقل یک حوزه انتخاب کن!",
    saved: "✅ تنظیمات ذخیره شد!\n⏳ در حال آماده‌سازی اخبار امروز برات... (حدود ۱ دقیقه)",
    saved2: "از فردا هر روز ساعت ۸ صبح اخبار مرتبط با علاقه‌مندی‌هات می‌رسه.\n\n/news — اخبار همین الان\n/start — تغییر تنظیمات\n/help — راهنما",
    news_wait: "⏳ در حال آماده‌سازی اخبار... حدود ۱ دقیقه صبر کن.",
    not_reg: "ابتدا /start بزن تا زبان و علاقه‌مندی‌هات را انتخاب کنی.",
    help: "📚 راهنما\n/news — اخبار همین الان\n/start — تغییر زبان یا علاقه‌مندی\n/help — این پیام\n\nهر روز ۸ صبح تهران اخبار می‌رسد.",
  },
  en: {
    welcome: "Hello! 👋 Choose your language:",
    choose_int: "Select your areas of interest (multiple allowed):",
    done_btn: "✅ Confirm & Get News",
    no_interest: "⚠️ Select at least one area!",
    saved: "✅ Settings saved!\n⏳ Preparing today's news for you... (about 1 min)",
    saved2: "From tomorrow you'll get relevant news every morning at 8AM Tehran time.\n\n/news — Get news now\n/start — Change settings\n/help — Help",
    news_wait: "⏳ Preparing news... about 1 minute.",
    not_reg: "Please /start first to set your language and interests.",
    help: "📚 Help\n/news — Get news now\n/start — Change language/interests\n/help — This message\n\nNews sent daily at 8AM Tehran time.",
  },
};

// ─────────────────────────────────────────────
// Telegram helpers
// ─────────────────────────────────────────────
async function tg(env, method, payload) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

function sendMessage(env, chat_id, text, keyboard) {
  const payload = { chat_id, text, parse_mode: "Markdown", disable_web_page_preview: true };
  if (keyboard) payload.reply_markup = keyboard;
  return tg(env, "sendMessage", payload);
}

function editMessageText(env, chat_id, message_id, text, keyboard) {
  const payload = { chat_id, message_id, text, parse_mode: "Markdown" };
  if (keyboard) payload.reply_markup = keyboard;
  return tg(env, "editMessageText", payload);
}

function editMessageReplyMarkup(env, chat_id, message_id, keyboard) {
  return tg(env, "editMessageReplyMarkup", { chat_id, message_id, reply_markup: keyboard });
}

function answerCallback(env, callback_id, text, alert) {
  const payload = { callback_query_id: callback_id };
  if (text) { payload.text = text; payload.show_alert = !!alert; }
  return tg(env, "answerCallbackQuery", payload);
}

function langKeyboard() {
  return { inline_keyboard: [[
    { text: "🇮🇷 فارسی", callback_data: "lang_fa" },
    { text: "🇬🇧 English", callback_data: "lang_en" },
  ]] };
}

function interestsKeyboard(lang, selected) {
  const items = lang === "fa" ? INTERESTS_FA : INTERESTS_EN;
  const kb = Object.entries(items).map(([key, label]) => {
    const tick = selected.includes(key) ? "✓ " : "";
    return [{ text: tick + label, callback_data: `int_${key}` }];
  });
  kb.push([{ text: TEXTS[lang].done_btn, callback_data: "int_done" }]);
  return { inline_keyboard: kb };
}

// ─────────────────────────────────────────────
// Google Sheets via service account JWT (RS256)
// ─────────────────────────────────────────────
function base64url(buf) {
  let str = typeof buf === "string" ? btoa(buf) : btoa(String.fromCharCode(...new Uint8Array(buf)));
  return str.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function pemToArrayBuffer(pem) {
  const b64 = pem.replace(/-----BEGIN PRIVATE KEY-----/, "")
                 .replace(/-----END PRIVATE KEY-----/, "")
                 .replace(/\s+/g, "");
  const raw = atob(b64);
  const buf = new ArrayBuffer(raw.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < raw.length; i++) view[i] = raw.charCodeAt(i);
  return buf;
}

async function getGoogleAccessToken(env) {
  const creds = JSON.parse(env.GOOGLE_CREDENTIALS_JSON);
  const now = Math.floor(Date.now() / 1000);

  const header = { alg: "RS256", typ: "JWT" };
  const claims = {
    iss: creds.client_email,
    scope: "https://www.googleapis.com/auth/spreadsheets",
    aud: "https://oauth2.googleapis.com/token",
    exp: now + 3600,
    iat: now,
  };

  const encHeader = base64url(JSON.stringify(header));
  const encClaims = base64url(JSON.stringify(claims));
  const signInput = `${encHeader}.${encClaims}`;

  const keyData = pemToArrayBuffer(creds.private_key);
  const cryptoKey = await crypto.subtle.importKey(
    "pkcs8", keyData,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["sign"]
  );
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5", cryptoKey, new TextEncoder().encode(signInput)
  );
  const jwt = `${signInput}.${base64url(signature)}`;

  const resp = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=${jwt}`,
  });
  const data = await resp.json();
  return data.access_token;
}

async function sheetsGetRows(env, token) {
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${env.GOOGLE_SHEET_ID}/values/${SHEET_NAME}!A:F`;
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  const data = await r.json();
  return data.values || [];
}

async function sheetsUpdateRow(env, token, rowIndex, values) {
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${env.GOOGLE_SHEET_ID}/values/${SHEET_NAME}!A${rowIndex}:F${rowIndex}?valueInputOption=RAW`;
  await fetch(url, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ values: [values] }),
  });
}

async function sheetsAppendRow(env, token, values) {
  const url = `https://sheets.googleapis.com/v4/spreadsheets/${env.GOOGLE_SHEET_ID}/values/${SHEET_NAME}!A:F:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ values: [values] }),
  });
}

async function sheetsEnsureHeader(env, token) {
  const rows = await sheetsGetRows(env, token);
  const header = ["chat_id", "name", "lang", "interests", "created_at", "updated_at"];
  if (!rows.length || JSON.stringify(rows[0]) !== JSON.stringify(header)) {
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${env.GOOGLE_SHEET_ID}/values/${SHEET_NAME}!A1?valueInputOption=RAW`;
    await fetch(url, {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ values: [header] }),
    });
  }
}

async function getUser(env, token, chatId) {
  const rows = await sheetsGetRows(env, token);
  if (rows.length < 2) return null;
  const header = rows[0];
  for (let i = 1; i < rows.length; i++) {
    if (rows[i][0] === String(chatId)) {
      const obj = {};
      header.forEach((h, idx) => (obj[h] = rows[i][idx] || ""));
      obj._rowIndex = i + 1;
      return obj;
    }
  }
  return null;
}

async function saveUser(env, token, chatId, name, lang, interests) {
  await sheetsEnsureHeader(env, token);
  const nowStr = new Date(Date.now() + (3.5 * 3600 * 1000)).toISOString().slice(0, 16).replace("T", " ");
  const existing = await getUser(env, token, chatId);
  if (existing) {
    await sheetsUpdateRow(env, token, existing._rowIndex,
      [String(chatId), name, lang, interests, existing.created_at || nowStr, nowStr]);
  } else {
    await sheetsAppendRow(env, token, [String(chatId), name, lang, interests, nowStr, nowStr]);
  }
}

// ─────────────────────────────────────────────
// GitHub Actions dispatch — triggers the heavy pipeline for ONE user
// ─────────────────────────────────────────────
async function triggerPersonalNews(env, chatId, lang, interests) {
  const url = `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/send-personal-news.yml/dispatches`;
  await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `token ${env.GH_PAT_FOR_WORKER}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: "main",
      inputs: { chat_id: String(chatId), lang, interests: interests.join(",") },
    }),
  });
}

// ─────────────────────────────────────────────
// Update handlers
// ─────────────────────────────────────────────
async function handleMessage(env, msg) {
  const chatId = msg.chat.id;
  const text = (msg.text || "").trim();
  const cmd = text.split(" ")[0].toLowerCase();

  if (cmd === "/start" || cmd === "/lang") {
    await sendMessage(env, chatId, TEXTS.fa.welcome, langKeyboard());
    return;
  }

  const token = await getGoogleAccessToken(env);
  const user = await getUser(env, token, chatId);
  const lang = user?.lang || "fa";

  if (cmd === "/news") {
    if (!user || !user.interests) {
      await sendMessage(env, chatId, TEXTS[lang].not_reg);
      return;
    }
    await sendMessage(env, chatId, TEXTS[lang].news_wait);
    await triggerPersonalNews(env, chatId, lang, user.interests.split(","));
    return;
  }

  if (cmd === "/help") {
    await sendMessage(env, chatId, TEXTS[lang].help);
    return;
  }
}

async function handleCallback(env, cq) {
  const chatId = cq.message.chat.id;
  const messageId = cq.message.message_id;
  const data = cq.data;
  const name = cq.from.first_name || cq.from.username || "Unknown";

  await answerCallback(env, cq.id);
  const token = await getGoogleAccessToken(env);

  if (data.startsWith("lang_")) {
    const lang = data.split("_")[1];
    const existing = await getUser(env, token, chatId);
    const interests = existing?.interests || "";
    await saveUser(env, token, chatId, name, lang, interests);

    const selected = interests ? interests.split(",") : [];
    await editMessageText(env, chatId, messageId, TEXTS[lang].choose_int, interestsKeyboard(lang, selected));
    return;
  }

  if (data.startsWith("int_") && data !== "int_done") {
    const key = data.replace("int_", "");
    const existing = await getUser(env, token, chatId);
    const lang = existing?.lang || "fa";
    let current = existing?.interests ? existing.interests.split(",").filter(Boolean) : [];

    if (current.includes(key)) current = current.filter((k) => k !== key);
    else current.push(key);

    await saveUser(env, token, chatId, name, lang, current.join(","));
    await editMessageReplyMarkup(env, chatId, messageId, interestsKeyboard(lang, current));
    return;
  }

  if (data === "int_done") {
    const existing = await getUser(env, token, chatId);
    const lang = existing?.lang || "fa";
    const interests = existing?.interests ? existing.interests.split(",").filter(Boolean) : [];

    if (!interests.length) {
      await answerCallback(env, cq.id, TEXTS[lang].no_interest, true);
      return;
    }

    await editMessageText(env, chatId, messageId, TEXTS[lang].saved);
    await triggerPersonalNews(env, chatId, lang, interests);
    await sendMessage(env, chatId, TEXTS[lang].saved2);
    return;
  }
}

// ─────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Design News Bot webhook is alive.", { status: 200 });
    }

    // Verify Telegram secret token
    const secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (env.WEBHOOK_SECRET && secret !== env.WEBHOOK_SECRET) {
      return new Response("Forbidden", { status: 403 });
    }

    let update;
    try {
      update = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    try {
      if (update.message && update.message.text) {
        await handleMessage(env, update.message);
      } else if (update.callback_query) {
        await handleCallback(env, update.callback_query);
      }
    } catch (e) {
      console.error("handler error:", e);
    }

    return new Response("OK", { status: 200 });
  },
};
