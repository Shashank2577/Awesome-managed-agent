FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

RUN pip install --no-cache-dir --timeout 120 --retries 5 "openai>=1.0" "httpx>=0.27"

COPY --chown=atrium:atrium universal_entrypoint.py /app/universal_entrypoint.py

USER atrium
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/universal_entrypoint.py"]
