# Authentication

## API Key Model

SLACathon uses static bearer tokens delivered via the `X-API-Key` HTTP header. Keys are 32-byte URL-safe random strings (`secrets.token_urlsafe(32)`), stored hashed in SQLite.

Protected endpoints:

```
POST /validate
GET  /jobs/{job_id}
POST /submit
GET  /history
```

Example:
```bash
curl -X POST https://your-domain.com/slacathon26/validate \
  -H "X-API-Key: YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"input": {"q1": 1.5, "q2": -2.0, "q3": 0.5, "d2": 1.0, "d3": 0.8}}'
```

## Getting an API Key

Keys are issued automatically at the end of the email verification flow.

```
1. POST /register      → sends verification email
2. Click link in email → GET /verify?token=<tok>
3. POST /verify        → key emailed to you
4. Use key in X-API-Key header
```

Lost key? `POST /resend-key` with your email re-sends it.

## CAPTCHA

Registration and verification forms require solving an [Altcha](https://altcha.org/) proof-of-work CAPTCHA. The frontend fetches a challenge from `GET /captcha-challenge` and includes the solved payload in form submissions. Server-side verification uses `SLACATHON_ALTCHA_HMAC_KEY`.

## Key Rotation

There is no automated key rotation. If a key is compromised, remove the user row from SQLite manually and ask the participant to re-register.

## Expiry

Unverified accounts expire after `SLACATHON_VERIFY_TIMEOUT_HOURS` (default 24 h). Verified keys do not expire.
