# easyHouse auth worker

Free-tier Cloudflare Worker + D1 for account signup, email verification, and rental alert delivery.

Scraping and listing data stay on the user's machine. This service only stores auth state and sends email through your Gmail app password.

## Setup

```bash
cd cloudflare/auth-worker
npm install
npx wrangler login
npx wrangler d1 create easyhouse-auth
```

Copy the `database_id` from the create output into `wrangler.jsonc`, then from the repo root:

```bash
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-gmail-app-password
export SMTP_FROM="easyHouse <you@gmail.com>"
./scripts/deploy_auth_worker.sh
```

## Local development

```bash
npm run db:migrate:local
npx wrangler secret put SMTP_USER
npx wrangler secret put SMTP_PASSWORD
npm run dev
```

Point the local agent at the dev URL:

```bash
python scripts/set_auth_url.py http://127.0.0.1:8787
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health |
| GET | `/auth/status` | Current session |
| POST | `/auth/signup` | Create account + send code |
| POST | `/auth/login` | Sign in |
| POST | `/auth/logout` | Sign out |
| POST | `/auth/verify` | Verify 6-digit code |
| POST | `/auth/resend-verification` | Resend code |
| PUT | `/auth/alerts` | Toggle alerts |
| POST | `/auth/notify` | Send listing alert email |
