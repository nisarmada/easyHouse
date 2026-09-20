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

async function readSmtpResponse(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  decoder: TextDecoder,
  buffer: { value: string },
): Promise<string> {
  while (true) {
    while (buffer.value.includes("\r\n")) {
      const index = buffer.value.indexOf("\r\n");
      const line = buffer.value.slice(0, index);
      buffer.value = buffer.value.slice(index + 2);
      if (/^\d{3} /.test(line)) {
        return line;
      }
    }
    const { value, done } = await reader.read();
    if (done) {
      throw new Error("SMTP connection closed unexpectedly");
    }
    buffer.value += decoder.decode(value, { stream: true });
  }
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
  const username = env.SMTP_USER?.trim();
  const password = env.SMTP_PASSWORD?.replace(/\s/g, "") || "";
  if (!username || !password) {
    throw new Error("SMTP credentials are not configured on the auth worker");
  }

  const host = env.SMTP_HOST || "smtp.gmail.com";
  const port = Number(env.SMTP_PORT || 465);
  const from = env.SMTP_FROM || `easyHouse <${username}>`;
  const mime = buildMime(from, payload);
  const secureTransport = port === 465 ? "on" : "starttls";

  let socket = connect({ hostname: host, port }, { secureTransport });
  await socket.opened;

  let reader = socket.readable.getReader();
  let writer = socket.writable.getWriter();
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  const buffer = { value: "" };

  async function command(text: string, expected = 250): Promise<string> {
    if (text) {
      await writer.write(encoder.encode(`${text}\r\n`));
    }
    const line = await readSmtpResponse(reader, decoder, buffer);
    await expectCode(line, expected);
    return line;
  }

  try {
    await readSmtpResponse(reader, decoder, buffer);
    await command("EHLO easyhouse", 250);

    if (port !== 465) {
      await command("STARTTLS", 220);
      await reader.cancel();
      await writer.close();
      socket = socket.startTls();
      await socket.opened;
      reader = socket.readable.getReader();
      writer = socket.writable.getWriter();
      buffer.value = "";
      await readSmtpResponse(reader, decoder, buffer);
      await command("EHLO easyhouse", 250);
    }

    const auth = encodeBase64(`\0${username}\0${password}`);
    await command(`AUTH PLAIN ${auth}`, 235);
    await command(`MAIL FROM:<${username}>`, 250);
    await command(`RCPT TO:<${payload.to}>`, 250);
    await command("DATA", 354);
    await writer.write(encoder.encode(`${mime}\r\n.\r\n`));
    const dataResponse = await readSmtpResponse(reader, decoder, buffer);
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
