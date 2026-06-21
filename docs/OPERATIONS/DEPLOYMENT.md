# ORBITIQ-X — Deployment Guide

## Quick Start (Production)

```bash
# 1. Clone and configure
git clone https://github.com/mahin-aeroai/ORBITIQ-X.git
cd ORBITIQ-X
cp .env.example .env
# Edit .env — replace ALL CHANGE_ME values

# 2. Generate secret key
echo "ORBITIQ_SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 3. Set production environment
sed -i 's/ORBITIQ_ENV=development/ORBITIQ_ENV=production/' .env
sed -i 's/BACKEND_RELOAD=true/BACKEND_RELOAD=false/' .env

# 4. Start infrastructure
docker compose -f deployment/docker/docker-compose.prod.yml up -d \
  postgres redis neo4j weaviate minio prometheus grafana

# 5. Wait for databases to be healthy
./deployment/scripts/health-check.sh

# 6. Start application
docker compose -f deployment/docker/docker-compose.prod.yml up -d \
  backend frontend nginx

# 7. Bootstrap first admin user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@your-domain.com","username":"admin","password":"SecurePass1","role":"admin"}'

# 8. Verify platform health
curl http://localhost:8000/api/v1/platform/health | jq .overall
```

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 8 cores | 16 cores |
| RAM | 16 GB | 32 GB |
| Storage | 100 GB SSD | 500 GB NVMe |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| Docker | 24.0+ | 26.0+ |

## Environment Variables

All variables documented in `.env.example`. Critical production settings:

```bash
ORBITIQ_ENV=production           # Enables TrustedHost, HSTS, prod logging
ORBITIQ_SECRET_KEY=<64-hex>      # JWT signing key — must be 32+ chars
BACKEND_RELOAD=false             # Never true in production
BACKEND_WORKERS=4                # Match CPU cores / 2
BACKEND_CORS_ORIGINS=https://app.your-domain.com
TRUSTED_HOSTS=api.your-domain.com,your-domain.com
```

## TLS/SSL Setup

Place certificates at paths from `SSL_CERT_PATH` and `SSL_KEY_PATH` in `.env`.

For Let's Encrypt:
```bash
certbot certonly --standalone -d api.your-domain.com
# Set SSL_CERT_PATH=/etc/letsencrypt/live/api.your-domain.com/fullchain.pem
# Set SSL_KEY_PATH=/etc/letsencrypt/live/api.your-domain.com/privkey.pem
```

## Scaling

The backend is stateless (JWT auth, Redis for shared state). Scale horizontally:
```bash
docker compose -f deployment/docker/docker-compose.prod.yml up -d --scale backend=4
```

Update Nginx upstream accordingly.
