package main

import (
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/MicahParks/jwkset"
)

const (
	logErr = "error"
)

func main() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	l := slog.Default()

	es := newExternalServer(l)
	es.newKeys(ctx)

	server := httptest.NewServer(es)

	u, err := url.ParseRequestURI(server.URL)
	if err != nil {
		l.ErrorContext(ctx, "Failed to parse URL.",
			logErr, err,
		)
		os.Exit(1)
	}

	refreshInterval := time.Second
	options := jwkset.HTTPClientStorageOptions{
		Ctx: ctx,
		RefreshErrorHandler: func(ctx context.Context, err error) {
			l.ErrorContext(ctx, "Failed to refresh keys.")
			os.Exit(1)
		},
		RefreshInterval: refreshInterval,
	}
	client, err := jwkset.NewStorageFromHTTP(u, options)
	if err != nil {
		l.ErrorContext(ctx, "Failed to create HTTP client storage.",
			logErr, err,
		)
		os.Exit(1)
	}

	oldKeys, err := client.KeyReadAll(ctx)
	if err != nil {
		l.ErrorContext(ctx, "Failed to read keys.",
			logErr, err,
		)
		os.Exit(1)
	}

	es.newKeys(ctx)
	time.Sleep(2 * refreshInterval)

	newKeys, err := client.KeyReadAll(ctx)
	if err != nil {
		l.ErrorContext(ctx, "Failed to read keys.",
			logErr, err,
		)
		os.Exit(1)
	}

	for _, oldKey := range oldKeys {
		l.InfoContext(ctx, "Old key.",
			"kid", oldKey.Marshal().KID,
		)
	}
	for _, newKey := range newKeys {
		l.InfoContext(ctx, "New key.",
			"kid", newKey.Marshal().KID,
		)
	}
}

type externalServer struct {
	l     *slog.Logger
	mux   sync.RWMutex
	store jwkset.Storage
}

func newExternalServer(l *slog.Logger) *externalServer {
	e := &externalServer{
		l:     l,
		store: jwkset.NewMemoryStorage(),
	}
	return e
}

func (e *externalServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	e.mux.RLock()
	defer e.mux.RUnlock()
	raw, err := e.store.JSON(ctx)
	if err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		e.l.ErrorContext(ctx, "Failed to get JWK set as JSON.",
			logErr, err,
		)
		os.Exit(1)
		return
	}
	_, _ = w.Write(raw)
}

func (e *externalServer) newKeys(ctx context.Context) {
	m := jwkset.NewMemoryStorage()
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		e.l.ErrorContext(ctx, "Failed to generate new key.",
			logErr, err,
		)
		os.Exit(1)
	}
	jwk, err := jwkset.NewJWKFromKey(pub, jwkset.JWKOptions{
		Metadata: jwkset.JWKMetadataOptions{
			KID: uuid.New().String(),
		},
		Validate: jwkset.JWKValidateOptions{},
		X509:     jwkset.JWKX509Options{},
	})
	if err != nil {
		e.l.ErrorContext(ctx, "Failed to create JWK from key.",
			logErr, err,
		)
		os.Exit(1)
	}
	err = m.KeyWrite(ctx, jwk)
	if err != nil {
		e.l.ErrorContext(ctx, "Failed to write new key to storage.",
			logErr, err,
		)
		os.Exit(1)
	}
	e.mux.Lock()
	e.store = m
	e.mux.Unlock()
}