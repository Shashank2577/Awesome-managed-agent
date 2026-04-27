FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/
COPY docs/ docs/

RUN pip install --no-cache-dir ".[all]"

EXPOSE 8080

CMD ["atrium", "serve", "--host", "0.0.0.0", "--port", "8080"]
