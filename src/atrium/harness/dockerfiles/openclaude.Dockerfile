FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep git curl jq ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

WORKDIR /app

# Pin openclaude to a specific tagged release.
RUN npm install -g openclaude@0.2.1

COPY --chown=atrium:atrium openclaude_entrypoint.js /app/openclaude_entrypoint.js

USER atrium
WORKDIR /workspace
ENV NODE_ENV=production

CMD ["node", "/app/openclaude_entrypoint.js", "--stream-json"]
