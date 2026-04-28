FROM python:3.12-slim

RUN useradd -u 10001 -m atrium
RUN mkdir -p /workspace /app && chown -R atrium:atrium /workspace /app

COPY --chown=atrium:atrium echo_runtime.py /app/echo_runtime.py

USER atrium
WORKDIR /workspace

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/echo_runtime.py"]
