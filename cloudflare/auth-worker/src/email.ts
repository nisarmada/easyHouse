import { connect } from "cloudflare:sockets";

export interface MailPayload {
  to: string;
  subject: string;
  plain: string;
  html?: string;
}

function encodeBase64(value: string): string {
  return btoa(unescape(encodeURIComponent(value)));
}

function buildMime(from: string, payload: MailPayload): string {
  const boundary = `easyhouse-${crypto.randomUUID()}`;
  const html = payload.html || payload.plain.replace(/\n/g, "<br>");
  return [
    `From: ${from}`,
    `To: ${payload.to}`,
    `Subject: ${payload.subject}`,
    "MIME-Version: 1.0",
    `Content-Type: multipart/alternative; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    "Content-Type: text/plain; charset=UTF-8",
    "",
    payload.plain,
    "",
    `--${boundary}`,
    "Content-Type: text/html; charset=UTF-8",
    "",
    html,
    "",
    `--${boundary}--`,
    "",
  ].join("\r\n");
}

async function readResponse(reader: ReadableStreamDefaultReader<Uint8Array>, decoder: TextDecoder): Promise<string> {
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    if (buffer.includes("\r\n")) break;
  }
  return buffer.trim();
}

async function expectCode(line: string, code: number): Promise<void> {
  if (!line.startsWith(String(code))) {
    throw new Error(`SMTP error (${code} expected): ${line}`);
  }
}

export async function sendServiceEmail(
  env: {
    SMTP_HOST?: string;
    SMTP_PORT?: string;
    SMTP_FROM?: string;
    SMTP_USER?: string;
    SMTP_PASSWORD?: string;
  },
  payload: MailPayload,
): Promise<void> {
  if (!env.SMTP_USER || !env.SMTP_PASSWORD) {
    throw new Error("SMTP credentials are not configured on the auth worker");
  }

  const host = env.SMTP_HOST || "smtp.gmail.com";
  const port = Number(env.SMTP_PORT || 465);
  const from = env.SMTP_FROM || `easyHouse <${env.SMTP_USER}>`;
  const mime = buildMime(from, payload);

  const socket = connect({
    hostname: host,
    port,
    secureTransport: port === 465 ? "on" : "starttls",
  });

  const reader = socket.readable.getReader();
  const writer = socket.writable.getWriter();
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  async function command(text: string, expected = 250): Promise<string> {
    await writer.write(encoder.encode(`${text}\r\n`));
    const line = await readResponse(reader, decoder);
    await expectCode(line, expected);
    return line;
  }

  try {
    await readResponse(reader, decoder);
    await command(`EHLO easyhouse`, 250);
    await command("AUTH LOGIN", 334);
    await command(encodeBase64(env.SMTP_USER), 334);
    await command(encodeBase64(env.SMTP_PASSWORD), 235);
    await command(`MAIL FROM:<${env.SMTP_USER}>`, 250);
    await command(`RCPT TO:<${payload.to}>`, 250);
    await command("DATA", 354);
    await writer.write(encoder.encode(`${mime}\r\n.\r\n`));
    const dataResponse = await readResponse(reader, decoder);
    await expectCode(dataResponse, 250);
    await command("QUIT", 221);
  } finally {
    try {
      await writer.close();
    } catch {
      /* ignore */
    }
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
  }
}

export function verificationEmail(code: string): MailPayload {
  return {
    to: "",
    subject: "Your easyHouse verification code",
    plain: [
      "Welcome to easyHouse.",
      "",
      `Your verification code is: ${code}`,
      "",
      "Enter this code in the app to confirm your email and receive rental alerts.",
      "The code expires in 15 minutes.",
    ].join("\n"),
    html: [
      "<html><body>",
      "<p>Welcome to easyHouse.</p>",
      "<p>Your verification code is:</p>",
      `<p style="font-size:28px;font-weight:700;letter-spacing:4px">${code}</p>`,
      "<p>Enter this code in the app to confirm your email and receive rental alerts.</p>",
      "<p>The code expires in 15 minutes.</p>",
      "</body></html>",
    ].join(""),
  };
}
