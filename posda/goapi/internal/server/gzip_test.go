package server

import (
	"bytes"
	"compress/gzip"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func gzipRequest(t *testing.T, handler http.Handler, acceptGzip bool) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest("GET", "/", nil)
	if acceptGzip {
		req.Header.Set("Accept-Encoding", "gzip")
	}
	rec := httptest.NewRecorder()
	Gzip(handler).ServeHTTP(rec, req)
	return rec
}

func TestGzipSmallResponsePassthrough(t *testing.T) {
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("tiny"))
	})
	rec := gzipRequest(t, h, true)
	if rec.Header().Get("Content-Encoding") != "" {
		t.Error("small response should not be compressed")
	}
	if rec.Body.String() != "tiny" {
		t.Errorf("body = %q", rec.Body.String())
	}
}

func TestGzipLargeResponseCompressed(t *testing.T) {
	payload := strings.Repeat("x", 2000)
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(payload))
	})
	rec := gzipRequest(t, h, true)
	if rec.Header().Get("Content-Encoding") != "gzip" {
		t.Fatal("large response should be compressed")
	}
	gz, err := gzip.NewReader(bytes.NewReader(rec.Body.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	out, err := io.ReadAll(gz)
	if err != nil {
		t.Fatal(err)
	}
	if string(out) != payload {
		t.Error("decompressed body does not match")
	}
}

func TestGzipNotAcceptedPassthrough(t *testing.T) {
	payload := strings.Repeat("x", 2000)
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(payload))
	})
	rec := gzipRequest(t, h, false)
	if rec.Header().Get("Content-Encoding") != "" {
		t.Error("response should not be compressed without Accept-Encoding")
	}
	if rec.Body.String() != payload {
		t.Error("body mismatch")
	}
}

func TestGzipStatusPreserved(t *testing.T) {
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		_, _ = w.Write([]byte(`{"detail":"Not Found"}`))
	})
	rec := gzipRequest(t, h, true)
	if rec.Code != http.StatusNotFound {
		t.Errorf("status = %d", rec.Code)
	}
}

func TestGzipStreamedResponseCompressed(t *testing.T) {
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("chunk1"))
		w.(http.Flusher).Flush()
		_, _ = w.Write([]byte("chunk2"))
	})
	rec := gzipRequest(t, h, true)
	if rec.Header().Get("Content-Encoding") != "gzip" {
		t.Fatal("streamed response should be compressed")
	}
	gz, err := gzip.NewReader(bytes.NewReader(rec.Body.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	out, _ := io.ReadAll(gz)
	if string(out) != "chunk1chunk2" {
		t.Errorf("decompressed = %q", out)
	}
}
