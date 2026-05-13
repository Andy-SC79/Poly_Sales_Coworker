# ====================================================
# Poly AI Coworker — Main Dockerfile (Simplified)
# ====================================================
FROM python:3.11-slim AS app

WORKDIR /app

# Install system dependencies (for asyncpg, audio libs, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source code
COPY . .

# Create non-root user for security
RUN addgroup --system poly && adduser --system --group poly
USER poly

EXPOSE 8000

# Default startup command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
