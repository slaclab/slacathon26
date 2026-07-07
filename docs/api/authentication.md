# Authentication

## API Key

All protected endpoints require the `X-API-Key` HTTP header:

```
X-API-Key: your_api_key
```

Keys are issued during the [registration flow](../getting-started/quickstart.md). The key is emailed to the registered address after email verification.

### Key Validation

The backend performs a database lookup on every request:

1. Query `User` table for `api_key = <header value>`
2. Check `User.verified = True`
3. Reject with `401 Unauthorized` if not found or not verified

### Dev Seed Keys

A fresh database is seeded with three keys for development:

| API Key | Display Name |
|---------|-------------|
| `key_123` | Alex |
| `key_456` | Chris |
| `key_789` | Ken |

These are inserted by `seed_dev_users()` in `app/db.py` on first startup.

## CAPTCHA (Registration Only)

Registration, verification, and resend-key endpoints require an Altcha proof-of-work CAPTCHA payload. Altcha is self-hosted — no external service is contacted.

### Flow

1. Fetch a challenge: `GET /captcha-challenge`
2. The Altcha JavaScript widget on the page solves the challenge in the browser
3. The solved payload (base64-encoded JSON) is submitted with the form as `altcha_payload`

### Challenge Response

```json
{
  "algorithm": "SHA-256",
  "challenge": "<hex>",
  "salt": "<hex>",
  "signature": "<hmac>"
}
```

The HMAC is signed with `SLACATHON_ALTCHA_HMAC_KEY`. Change this key in production.

### Verification

`verify_captcha(payload)` in `app/captcha.py` decodes and verifies the solution. Returns `400` on failure.
