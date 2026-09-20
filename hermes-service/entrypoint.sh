#!/bin/sh
set -e

# Materialize the profile + backend .env files from Railway-injected env vars
# at container start — Hermes reads its secrets from a profile .env FILE, not
# from ambient process env (confirmed: passing OPENAI_API_KEY/API_SERVER_KEY
# via the shell alone did NOT enable the API server in local testing; only
# writing them into the profile's own .env did).

mkdir -p /root/.hermes/profiles/the01dev
cp /app/hermes-service/config.yaml /root/.hermes/profiles/the01dev/config.yaml

cat > /root/.hermes/profiles/the01dev/.env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
API_SERVER_ENABLED=true
API_SERVER_KEY=${API_SERVER_KEY}
API_SERVER_PORT=${PORT:-8642}
API_SERVER_HOST=0.0.0.0
DATABASE_URL=${DATABASE_URL}
EOF

# the01dev_tools.py (the MCP server) loads backend/.env itself for its own
# DB/OpenAI access — same values, separate file, since it's a separate
# process Hermes spawns.
cat > /app/backend/.env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
DATABASE_URL=${DATABASE_URL}
EOF

exec hermes -p the01dev gateway run
