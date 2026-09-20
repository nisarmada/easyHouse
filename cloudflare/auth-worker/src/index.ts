import { hashPassword, verifyPassword } from "./password";
import { sendServiceEmail, verificationEmail, type MailPayload } from "./email";

export interface Env {
  DB: D1Database;
  SMTP_HOST?: string;
  SMTP_PORT?: string;
  SMTP_FROM?: string;
  SMTP_USER?: string;
  SMTP_PASSWORD?: string;
}

type AccountRow = {
  id: string;
  email: string;
  password_hash: string;
  verified_at: string | null;
  alerts_enabled: number;
};

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type",
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

function error(message: string, status = 400): Response {
  return json({ detail: message }, status);
}

function validateEmail(email: string): string {
  const cleaned = email.trim().toLowerCase();
  if (!cleaned.includes("@") || cleaned.startsWith("@") || cleaned.endsWith("@")) {
    throw new Error("Enter a valid email address");
  }
  return cleaned;
}

function validatePassword(password: string): void {
  if (password.length < 8) throw new Error("Password must be at least 8 characters");
}

function normalizeCode(code: string): string {
  const digits = [...code].filter((ch) => /\d/.test(ch)).join("");
  if (digits.length !== 6) throw new Error("Enter the 6-digit verification code");
  return digits;
}

function accountPublic(row: AccountRow) {
  return {
    email: row.email,
    verified: row.verified_at != null,
    alerts_enabled: Boolean(row.alerts_enabled),
  };
}

function randomToken(bytes = 32): string {
  return [...crypto.getRandomValues(new Uint8Array(bytes))]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function verificationCode(): string {
  return String(Math.floor(Math.random() * 1_000_000)).padStart(6, "0");
}

function expiresDays(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString();
}

function expiresMinutes(minutes: number): string {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

function bearerToken(request: Request): string | null {
  const header = request.headers.get("Authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : null;
}

async function getSessionAccount(env: Env, token: string): Promise<AccountRow | null> {
  const row = await env.DB.prepare(
    `SELECT a.id, a.email, a.password_hash, a.verified_at, a.alerts_enabled, s.expires_at
     FROM sessions s
     JOIN accounts a ON a.id = s.account_id
     WHERE s.token = ?`,
  )
    .bind(token)
    .first<AccountRow & { expires_at: string }>();

  if (!row) return null;
  if (new Date(row.expires_at).getTime() < Date.now()) {
    await env.DB.prepare("DELETE FROM sessions WHERE token = ?").bind(token).run();
    return null;
  }
  return row;
}

async function issueVerificationCode(env: Env, accountId: string, email: string): Promise<boolean> {
  const code = verificationCode();
  await env.DB.prepare("DELETE FROM verification_tokens WHERE account_id = ?").bind(accountId).run();
  await env.DB.prepare(
    "INSERT INTO verification_tokens (token, account_id, expires_at) VALUES (?, ?, ?)",
  )
    .bind(code, accountId, expiresMinutes(15))
    .run();

  try {
    const payload = verificationEmail(code);
    payload.to = email;
    await sendServiceEmail(env, payload);
    return true;
  } catch (err) {
    console.error("Could not send verification email:", err);
    return false;
  }
}

async function handleSignup(env: Env, body: { email?: string; password?: string }) {
  const email = validateEmail(body.email || "");
  validatePassword(body.password || "");

  const existing = await env.DB.prepare("SELECT id FROM accounts WHERE email = ?").bind(email).first();
  if (existing) throw new Error("An account with this email already exists");

  const accountId = crypto.randomUUID();
  const passwordHash = await hashPassword(body.password || "");
  await env.DB.prepare(
    "INSERT INTO accounts (id, email, password_hash) VALUES (?, ?, ?)",
  )
    .bind(accountId, email, passwordHash)
    .run();

  const sessionToken = randomToken();
  await env.DB.prepare(
    "INSERT INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
  )
    .bind(sessionToken, accountId, expiresDays(30))
    .run();

  const emailSent = await issueVerificationCode(env, accountId, email);
  const account = await env.DB.prepare(
    "SELECT id, email, password_hash, verified_at, alerts_enabled FROM accounts WHERE id = ?",
  )
    .bind(accountId)
    .first<AccountRow>();

  return json({
    session_token: sessionToken,
    account: accountPublic(account!),
    email_sent: emailSent,
    can_send_mail: Boolean(env.SMTP_USER && env.SMTP_PASSWORD),
  });
}

async function handleLogin(env: Env, body: { email?: string; password?: string }) {
  const email = validateEmail(body.email || "");
  const row = await env.DB.prepare(
    "SELECT id, email, password_hash, verified_at, alerts_enabled FROM accounts WHERE email = ?",
  )
    .bind(email)
    .first<AccountRow>();

  if (!row || !(await verifyPassword(body.password || "", row.password_hash))) {
    throw new Error("Invalid email or password");
  }

  const sessionToken = randomToken();
  await env.DB.prepare(
    "INSERT INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
  )
    .bind(sessionToken, row.id, expiresDays(30))
    .run();

  return json({
    session_token: sessionToken,
    account: accountPublic(row),
    can_send_mail: Boolean(env.SMTP_USER && env.SMTP_PASSWORD),
  });
}

async function handleVerify(env: Env, body: { code?: string }) {
  const code = normalizeCode(body.code || "");
  const row = await env.DB.prepare(
    `SELECT vt.token, vt.account_id, vt.expires_at
     FROM verification_tokens vt
     WHERE vt.token = ?`,
  )
    .bind(code)
    .first<{ token: string; account_id: string; expires_at: string }>();

  if (!row || new Date(row.expires_at).getTime() < Date.now()) {
    if (row) {
      await env.DB.prepare("DELETE FROM verification_tokens WHERE token = ?").bind(code).run();
    }
    throw new Error("Verification code is invalid or expired");
  }

  const now = new Date().toISOString();
  await env.DB.prepare("UPDATE accounts SET verified_at = ? WHERE id = ?").bind(now, row.account_id).run();
  await env.DB.prepare("DELETE FROM verification_tokens WHERE account_id = ?").bind(row.account_id).run();

  const account = await env.DB.prepare(
    "SELECT id, email, password_hash, verified_at, alerts_enabled FROM accounts WHERE id = ?",
  )
    .bind(row.account_id)
    .first<AccountRow>();

  return json(accountPublic(account!));
}

async function handleResend(env: Env, token: string) {
  const account = await getSessionAccount(env, token);
  if (!account) throw new Error("Session expired — sign in again");
  if (account.verified_at) throw new Error("Email is already verified");

  const emailSent = await issueVerificationCode(env, account.id, account.email);
  return json({ status: "sent", email_sent: emailSent });
}

async function handleAlerts(env: Env, token: string, enabled: boolean) {
  const account = await getSessionAccount(env, token);
  if (!account) throw new Error("Session expired — sign in again");
  if (enabled && !account.verified_at) throw new Error("Verify your email before enabling alerts");

  await env.DB.prepare("UPDATE accounts SET alerts_enabled = ? WHERE id = ?")
    .bind(enabled ? 1 : 0, account.id)
    .run();

  const refreshed = await env.DB.prepare(
    "SELECT id, email, password_hash, verified_at, alerts_enabled FROM accounts WHERE id = ?",
  )
    .bind(account.id)
    .first<AccountRow>();

  return json(accountPublic(refreshed!));
}

async function handleStatus(env: Env, token: string | null) {
  if (!token) {
    return json({
      signed_in: false,
      account: null,
      can_send_mail: Boolean(env.SMTP_USER && env.SMTP_PASSWORD),
    });
  }

  const account = await getSessionAccount(env, token);
  return json({
    signed_in: account != null,
    account: account ? accountPublic(account) : null,
    can_send_mail: Boolean(env.SMTP_USER && env.SMTP_PASSWORD),
  });
}

async function handleNotify(
  env: Env,
  token: string,
  body: { listings?: Array<{ title?: string; price_eur?: number | null; city?: string | null; url?: string }> },
) {
  const account = await getSessionAccount(env, token);
  if (!account) throw new Error("Session expired — sign in again");
  if (!account.verified_at || !account.alerts_enabled) {
    return json({ status: "skipped" });
  }

  const listings = body.listings || [];
  if (!listings.length) return json({ status: "skipped" });

  const count = listings.length;
  const plainLines = listings.map((listing) => {
    const price = listing.price_eur != null ? `€${listing.price_eur.toLocaleString("en-US")}` : "?";
    const city = listing.city ? ` (${listing.city})` : "";
    return `${price} — ${listing.title || "Listing"}${city}\n${listing.url || ""}`;
  });
  const htmlLines = listings.map((listing) => {
    const price = listing.price_eur != null ? `€${listing.price_eur.toLocaleString("en-US")}` : "?";
    const city = listing.city ? ` (${listing.city})` : "";
    const title = `${listing.title || "Listing"}${city}`;
    const url = listing.url || "";
    return `<p><strong>${price}</strong> — ${title}<br><a href="${url}">${url}</a></p>`;
  });

  const payload: MailPayload = {
    to: account.email,
    subject: `easyHouse: ${count} new listing${count === 1 ? "" : "s"}`,
    plain: `${count} new listing${count === 1 ? "" : "s"}\n\n${plainLines.join("\n\n")}`,
    html: `<html><body><p>${count} new listing${count === 1 ? "" : "s"}</p>${htmlLines.join("")}</body></html>`,
  };

  await sendServiceEmail(env, payload);
  return json({ status: "sent" });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/health") {
        return json({ status: "ok", can_send_mail: Boolean(env.SMTP_USER && env.SMTP_PASSWORD) });
      }

      if (path === "/auth/status" && request.method === "GET") {
        return handleStatus(env, bearerToken(request));
      }

      const body =
        request.method === "GET" || request.method === "HEAD"
          ? {}
          : ((await request.json().catch(() => ({}))) as Record<string, unknown>);

      if (path === "/auth/signup" && request.method === "POST") {
        return handleSignup(env, body as { email?: string; password?: string });
      }
      if (path === "/auth/login" && request.method === "POST") {
        return handleLogin(env, body as { email?: string; password?: string });
      }
      if (path === "/auth/logout" && request.method === "POST") {
        const token = bearerToken(request);
        if (token) {
          await env.DB.prepare("DELETE FROM sessions WHERE token = ?").bind(token).run();
        }
        return json({ status: "signed_out" });
      }
      if (path === "/auth/verify" && request.method === "POST") {
        return handleVerify(env, body as { code?: string });
      }
      if (path === "/auth/resend-verification" && request.method === "POST") {
        const token = bearerToken(request);
        if (!token) throw new Error("Not signed in");
        return handleResend(env, token);
      }
      if (path === "/auth/alerts" && request.method === "PUT") {
        const token = bearerToken(request);
        if (!token) throw new Error("Not signed in");
        return handleAlerts(env, token, Boolean((body as { enabled?: boolean }).enabled));
      }
      if (path === "/auth/notify" && request.method === "POST") {
        const token = bearerToken(request);
        if (!token) throw new Error("Not signed in");
        return handleNotify(env, token, body as { listings?: Array<Record<string, unknown>> });
      }

      return error("Not found", 404);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed";
      const status = message.includes("Not signed in") || message.includes("Session expired") ? 401 : 400;
      return error(message, status);
    }
  },
};
