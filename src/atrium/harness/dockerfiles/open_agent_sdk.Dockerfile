FROM node:22-slim

# Standard tools the harness expects
RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep git curl jq ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

WORKDIR /app

# Pin the version. Bump intentionally via PR.
RUN npm install -g @shipany/open-agent-sdk@0.4.2

COPY --chown=atrium:atrium oas_entrypoint.js /app/oas_entrypoint.js

USER atrium
WORKDIR /workspace
ENV NODE_ENV=production

CMD ["node", "/app/oas_entrypoint.js", "--stream-json"]
