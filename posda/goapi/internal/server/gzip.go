package server

import (
	"bytes"
	"compress/gzip"
	"net/http"
	"strings"
)

// gzipMinSize matches the Python GZipMiddleware configuration
// (minimum_size=500, compresslevel=9).
const (
	gzipMinSize = 500
	gzipLevel   = 9
)

// Gzip compresses responses for clients that accept it. Small,
// non-streamed responses (under gzipMinSize bytes) are passed through
// uncompressed; anything larger, or anything that streams (flushes),
// is gzipped — the same policy as Starlette's GZipMiddleware.
func Gzip(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") {
			next.ServeHTTP(w, r)
			return
		}
		gw := &gzipWriter{underlying: w, status: http.StatusOK}
		defer gw.finish()
		next.ServeHTTP(gw, r)
	})
}

type gzipWriter struct {
	underlying http.ResponseWriter
	status     int
	decided    bool
	useGzip    bool
	buf        bytes.Buffer
	gz         *gzip.Writer
}

func (g *gzipWriter) Header() http.Header {
	return g.underlying.Header()
}

func (g *gzipWriter) WriteHeader(status int) {
	g.status = status
}

func (g *gzipWriter) Write(p []byte) (int, error) {
	if !g.decided {
		g.buf.Write(p)
		if g.buf.Len() >= gzipMinSize {
			if err := g.decide(true); err != nil {
				return 0, err
			}
		}
		return len(p), nil
	}
	if g.useGzip {
		return g.gz.Write(p)
	}
	return g.underlying.Write(p)
}

// Flush marks the response as streamed: streamed responses are always
// compressed, regardless of size so far.
func (g *gzipWriter) Flush() {
	if !g.decided {
		if err := g.decide(true); err != nil {
			return
		}
	}
	if g.useGzip {
		_ = g.gz.Flush()
	}
	if f, ok := g.underlying.(http.Flusher); ok {
		f.Flush()
	}
}

// decide commits to compressing (or not), writes the response headers,
// and drains anything buffered so far.
func (g *gzipWriter) decide(useGzip bool) error {
	g.decided = true
	g.useGzip = useGzip
	h := g.underlying.Header()
	if useGzip {
		h.Set("Content-Encoding", "gzip")
		h.Del("Content-Length")
		h.Add("Vary", "Accept-Encoding")
	}
	g.underlying.WriteHeader(g.status)
	if g.buf.Len() == 0 {
		if useGzip {
			gz, err := gzip.NewWriterLevel(g.underlying, gzipLevel)
			if err != nil {
				return err
			}
			g.gz = gz
		}
		return nil
	}
	if useGzip {
		gz, err := gzip.NewWriterLevel(g.underlying, gzipLevel)
		if err != nil {
			return err
		}
		g.gz = gz
		_, err = g.gz.Write(g.buf.Bytes())
		g.buf.Reset()
		return err
	}
	_, err := g.underlying.Write(g.buf.Bytes())
	g.buf.Reset()
	return err
}

// finish is called once the handler returns: undecided responses were
// small enough to send uncompressed, and gzip streams must be closed.
func (g *gzipWriter) finish() {
	if !g.decided {
		_ = g.decide(false)
		return
	}
	if g.useGzip {
		_ = g.gz.Close()
	}
}
