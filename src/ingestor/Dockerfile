# Build stage
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Dependencies first (cache layer)
COPY go.mod go.sum* ./
RUN go mod download

# Build
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o ingestor .

# Runtime stage - minimal
FROM scratch

# SSL certificates for HTTPS
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Binary
COPY --from=builder /app/ingestor /ingestor

# Non-root user (UID 1000)
USER 1000

EXPOSE 8080

ENTRYPOINT ["/ingestor"]