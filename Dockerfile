FROM python:3.11-slim

WORKDIR /workspaces/slacathon26

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Stub package so pip can resolve metadata before full source is available
RUN mkdir -p src/slacathon && touch src/slacathon/__init__.py
RUN pip install --no-cache-dir -e .

COPY . .

CMD ["uvicorn", "slacathon.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
