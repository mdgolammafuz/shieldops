# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy dependencies
COPY --from=builder /app/deps /app/deps

# Copy application
COPY . .

# Set Python path
ENV PYTHONPATH=/app/deps:/app
ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd -r -u 1000 processor
USER 1000

EXPOSE 8080

CMD ["python", "main.py"]