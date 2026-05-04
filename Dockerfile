# Render (and other hosts): image build installs dependencies — no separate "build command" needed.
FROM python:3.11-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# py-solc-x / some wheels may need a compiler; curl for solc downloads
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render injects PORT; nomad_api reads it when RENDER=true
CMD ["python", "app.py"]
