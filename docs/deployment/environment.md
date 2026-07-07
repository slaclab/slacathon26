# Environment Variables

Full reference for all `SLACATHON_*` environment variables. Values are read from the environment or from a `.env` file in the project root.

See [Configuration](../getting-started/configuration.md) for descriptions and defaults.

## Production Checklist

| Variable | Action Required |
|----------|----------------|
| `SLACATHON_ALTCHA_HMAC_KEY` | **Change from default** — use a strong random value |
| `SLACATHON_SMTP_HOST` | Set to your production SMTP server |
| `SLACATHON_SMTP_FROM` | Set to a valid sender address |
| `SLACATHON_PUBLIC_URL` | Set to your public HTTPS base URL |
| `SLACATHON_ROOT_PATH` | Set to your reverse-proxy prefix |
| `SLACATHON_API_KEYS` | Remove or empty (use DB-registered keys only) |

## Minimal Production `.env`

```bash
SLACATHON_ACTIVE_TASK=flat_beam
SLACATHON_ROOT_PATH=/slacathon26
SLACATHON_HOST=127.0.0.1
SLACATHON_PORT=8888
SLACATHON_SMTP_HOST=smtp.example.com
SLACATHON_SMTP_PORT=587
SLACATHON_SMTP_FROM=noreply@example.com
SLACATHON_PUBLIC_URL=https://your-domain.com
SLACATHON_ALTCHA_HMAC_KEY=<64-char-random-hex>
SLACATHON_VERIFY_TIMEOUT_HOURS=24
SLACATHON_CLEANUP_INTERVAL_MINUTES=10
SLACATHON_LEADERBOARD_SIZE=15
SLACATHON_MAX_VALIDATIONS_PER_USER=10000
```
