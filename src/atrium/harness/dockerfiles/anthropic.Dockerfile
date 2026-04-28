FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ripgrep git curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

RUN pip install --no-cache-dir --timeout 120 --retries 5 "anthropic>=0.49.0"

COPY --chown=atrium:atrium anthropic_entrypoint.py /app/anthropic_entrypoint.py

USER atrium
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/anthropic_entrypoint.py"]
