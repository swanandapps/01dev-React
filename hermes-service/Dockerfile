# Hermes has no published Docker image — it's a git/pip install (confirmed by
# reading the actual install method of a working local instance: git clone +
# `pip install -e .`, Python 3.11). This Dockerfile reproduces that, pinned to
# the exact commit already tested against this backend all session.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Backend source + deps — the01dev_tools.py (the MCP server Hermes calls)
# imports app.services.* directly, so it needs the backend's code and
# dependencies in the same Python environment, not just Hermes's own.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend

# fastmcp — what the01dev_tools.py uses to expose its tools; not a backend
# dependency (the main FastAPI service never imports it), so it's installed
# here rather than added to backend/requirements.txt.
RUN pip install --no-cache-dir fastmcp==3.4.4

# Hermes itself, pinned to the exact commit this integration was built and
# tested against (github.com/NousResearch/hermes-agent).
RUN pip install --no-cache-dir "git+https://github.com/NousResearch/hermes-agent.git@080daa3f424f06bc3a27ec9deb9267d94db9a964"

# aiohttp isn't a core dependency of the base package — it's only pulled in
# via the [messaging]/[slack]/[teams]/etc. extras (confirmed by reading
# hermes-agent's own pyproject.toml). The API server adapter needs it too,
# but none of those extras. Install the exact version hermes-agent itself
# pins for its extras, rather than an unpinned "latest".
RUN pip install --no-cache-dir aiohttp==3.14.1

COPY hermes-service/config.yaml /app/hermes-service/config.yaml
COPY hermes-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8642

ENTRYPOINT ["/app/entrypoint.sh"]
