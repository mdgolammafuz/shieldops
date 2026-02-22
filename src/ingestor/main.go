// ShieldOps Ingestor
// Connects to CertStream, validates messages, publishes to NATS.
//
// Design: Slim, secure, robust.
// - Graceful shutdown on SIGTERM
// - Auto-reconnect on WebSocket failure
// - Input validation before publishing
// - Prometheus metrics
// - Structured JSON logging (slog)

package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"nhooyr.io/websocket"
)

// Config from environment
var (
	certstreamURL = getEnv("CERTSTREAM_URL", "wss://certstream.calidog.io")
	natsURL       = getEnv("NATS_URL", "nats://nats:4222")
	natsSubject   = getEnv("NATS_SUBJECT", "certs.validated")
	metricsPort   = getEnv("METRICS_PORT", "8080")
	logLevel      = getEnv("LOG_LEVEL", "info")
)

// Structured logger
var logger *slog.Logger

func initLogger() {
	var level slog.Level
	switch logLevel {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: level,
	})
	logger = slog.New(handler).With(
		slog.String("service", "ingestor"),
		slog.String("version", "1.0.0"),
	)
}

// Prometheus metrics
var (
	msgsReceived = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ingestor_messages_received_total",
		Help: "Total messages received from CertStream",
	})
	msgsValid = prometheus.NewCounter(prometheus.CounterOpts{
		Name: "ingestor_messages_valid_total",
		Help: "Valid messages published to NATS",
	})
	msgsInvalid = prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "ingestor_messages_invalid_total",
		Help: "Invalid messages by reason",
	}, []string{"reason"})
	wsConnected = prometheus.NewGauge(prometheus.GaugeOpts{
		Name: "ingestor_websocket_connected",
		Help: "WebSocket connection status (1=connected, 0=disconnected)",
	})
)

func init() {
	prometheus.MustRegister(msgsReceived, msgsValid, msgsInvalid, wsConnected)
}

// CertStream message structures (only what we need)
type certMessage struct {
	MessageType string   `json:"message_type"`
	Data        certData `json:"data"`
}

type certData struct {
	LeafCert leafCert `json:"leaf_cert"`
}

type leafCert struct {
	AllDomains  []string `json:"all_domains"`
	Fingerprint string   `json:"fingerprint"`
	Issuer      issuer   `json:"issuer"`
	NotBefore   float64  `json:"not_before"`
	NotAfter    float64  `json:"not_after"`
}

type issuer struct {
	O  string `json:"O"`
	CN string `json:"CN"`
}

// Validated output for NATS
type validatedCert struct {
	Domains     []string `json:"domains"`
	Fingerprint string   `json:"fingerprint"`
	Issuer      string   `json:"issuer"`
	NotBefore   int64    `json:"not_before"`
	NotAfter    int64    `json:"not_after"`
	ReceivedAt  int64    `json:"received_at"`
}

func main() {
	initLogger()
	logger.Info("starting ingestor",
		slog.String("certstream_url", certstreamURL),
		slog.String("nats_url", natsURL),
		slog.String("nats_subject", natsSubject),
	)

	// Start metrics server
	go func() {
		http.Handle("/metrics", promhttp.Handler())
		http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte("ok"))
		})
		logger.Info("metrics server started", slog.String("port", metricsPort))
		http.ListenAndServe(":"+metricsPort, nil)
	}()

	// Connect to NATS
	nc, err := nats.Connect(natsURL,
		nats.RetryOnFailedConnect(true),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		logger.Error("nats connection failed", slog.String("error", err.Error()))
		os.Exit(1)
	}
	defer nc.Close()
	logger.Info("connected to nats", slog.String("url", natsURL))

	// Graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
	go func() {
		sig := <-sigCh
		logger.Info("shutdown signal received", slog.String("signal", sig.String()))
		cancel()
	}()

	// Main loop with reconnection
	for {
		select {
		case <-ctx.Done():
			logger.Info("shutdown complete")
			return
		default:
			if err := stream(ctx, nc); err != nil {
				logger.Warn("stream error, reconnecting",
					slog.String("error", err.Error()),
					slog.Duration("retry_in", 5*time.Second),
				)
				wsConnected.Set(0)
				time.Sleep(5 * time.Second)
			}
		}
	}
}

func stream(ctx context.Context, nc *nats.Conn) error {
	conn, _, err := websocket.Dial(ctx, certstreamURL, nil)
	if err != nil {
		return err
	}
	defer conn.Close(websocket.StatusNormalClosure, "shutdown")

	logger.Info("connected to certstream", slog.String("url", certstreamURL))
	wsConnected.Set(1)

	for {
		select {
		case <-ctx.Done():
			return nil
		default:
			_, data, err := conn.Read(ctx)
			if err != nil {
				return err
			}
			msgsReceived.Inc()

			validated, reason := validate(data)
			if validated == nil {
				if reason != "" {
					msgsInvalid.WithLabelValues(reason).Inc()
					logger.Debug("message validation failed", slog.String("reason", reason))
				}
				continue
			}

			out, _ := json.Marshal(validated)
			if err := nc.Publish(natsSubject, out); err != nil {
				logger.Error("nats publish failed",
					slog.String("error", err.Error()),
					slog.String("fingerprint", validated.Fingerprint),
				)
				continue
			}
			msgsValid.Inc()

			// Log first domain for debugging (not all to avoid log spam)
			if len(validated.Domains) > 0 {
				logger.Debug("certificate published",
					slog.String("fingerprint", validated.Fingerprint),
					slog.String("domain", validated.Domains[0]),
					slog.Int("domain_count", len(validated.Domains)),
				)
			}
		}
	}
}

func validate(data []byte) (*validatedCert, string) {
	var msg certMessage
	if err := json.Unmarshal(data, &msg); err != nil {
		return nil, "json_parse"
	}

	// Skip non-certificate messages (heartbeats)
	if msg.MessageType != "certificate_update" {
		return nil, ""
	}

	// Validate required fields
	if len(msg.Data.LeafCert.AllDomains) == 0 {
		return nil, "no_domains"
	}
	if msg.Data.LeafCert.Fingerprint == "" {
		return nil, "no_fingerprint"
	}

	return &validatedCert{
		Domains:     msg.Data.LeafCert.AllDomains,
		Fingerprint: msg.Data.LeafCert.Fingerprint,
		Issuer:      msg.Data.LeafCert.Issuer.O,
		NotBefore:   int64(msg.Data.LeafCert.NotBefore),
		NotAfter:    int64(msg.Data.LeafCert.NotAfter),
		ReceivedAt:  time.Now().Unix(),
	}, ""
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}