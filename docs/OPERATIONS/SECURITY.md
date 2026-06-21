# ORBITIQ-X — Security Reference

## Security Architecture

```
Browser → Nginx (TLS 1.2/1.3) → FastAPI Backend
                                → Next.js Frontend

Auth: JWT HS256 (access: 60min) + refresh token (7d, SHA-256 hashed in DB)
RBAC: admin > operator > analyst > readonly
```

## Security Audit Results (Phase 14C)

| Control | Status | Notes |
|---|---|---|
| Secrets in source | ✅ NONE | Verified - no hardcoded secrets |
| JWT algorithm | ✅ HS256 | 64-char signing key enforced |
| Password hashing | ✅ bcrypt-12 | Timing-safe via passlib |
| Refresh tokens | ✅ SHA-256 stored | Raw token never in DB |
| Token rotation | ✅ On every /refresh | Old token immediately revoked |
| Account lockout | ✅ 5 attempts/15min | |
| CORS | ✅ Whitelist only | No wildcards |
| Security headers | ✅ All present | X-Frame-Options, CSP, HSTS (prod) |
| TLS | ✅ 1.2/1.3 only | Strong cipher suite |
| Rate limiting | ✅ Nginx + config | 100 req/min API, 10 req/min auth |
| Non-root container | ✅ orbitiq:1001 | |
| Input validation | ✅ Pydantic v2 | All request models validated |
| SQL injection | ✅ SQLAlchemy ORM | No raw queries |
| XSS | ✅ React + CSP | |
| Audit logging | ✅ audit_logs table | Immutable, append-only |

## Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| JWT secret compromise | CRITICAL | Rotate `ORBITIQ_SECRET_KEY` → all sessions invalidated |
| PostgreSQL credential leak | CRITICAL | Change pw → restart → check audit logs |
| Anthropic API key leak | HIGH | Rotate key, check billing for unexpected usage |
| Space-Track credential leak | HIGH | Change password, notify Space-Track |
| Redis credential leak | MEDIUM | Flush + change password |

## Secret Rotation Procedure

```bash
# 1. Rotate JWT secret (all users must re-login)
sed -i "s/ORBITIQ_SECRET_KEY=.*/ORBITIQ_SECRET_KEY=$(openssl rand -hex 32)/" .env
docker compose restart backend

# 2. Rotate PostgreSQL password
psql -U postgres -c "ALTER USER orbitiq WITH PASSWORD 'new-password';"
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=new-password/" .env
docker compose restart backend

# 3. Rotate Redis password
redis-cli CONFIG SET requirepass "new-password"
sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=new-password/" .env
docker compose restart backend redis
```
