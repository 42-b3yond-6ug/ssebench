The project's provided HTTP client's local JWK Set cache should do a full replacement when the goroutine refreshes the remote JWK Set. The current behavior is to overwrite or append. This is a security issue for use cases that utilize the provided auto-caching HTTP client and where key removal from a JWK Set is equivalent to revocation.

Regardless of this bug, please note that removing a key from a JWK Set does not equate to instant revocation for most use cases as it takes time for JWK Set updates to propagate to all clients.
Here's the Proof of Concept (POC) I wrote to confirm this bug:

POC output:

```
2025/01/08 20:21:17 INFO Old key. kid=836a7fb7-03a3-40cb-ab39-40235ed1de0c
2025/01/08 20:21:17 INFO New key. kid=836a7fb7-03a3-40cb-ab39-40235ed1de0c
2025/01/08 20:21:17 INFO New key. kid=ee966d68-6739-40d3-b652-c7ad023fa9cd
```

POC code:

```
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
```
