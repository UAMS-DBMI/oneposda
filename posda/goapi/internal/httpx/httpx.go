// Package httpx contains small helpers for writing handlers that match
// FastAPI's response conventions ({"detail": ...} error bodies, etc).
package httpx

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
)

// Error mirrors FastAPI's HTTPException: a status code plus a "detail"
// value serialized as {"detail": <detail>}.
type Error struct {
	Status  int
	Detail  any
	Headers map[string]string
}

func (e *Error) Error() string {
	return fmt.Sprintf("http %d: %v", e.Status, e.Detail)
}

func NewError(status int, detail any) *Error {
	return &Error{Status: status, Detail: detail}
}

// HandlerFunc is an http handler that may return an error. Errors of
// type *Error become {"detail": ...} responses with the given status;
// anything else becomes a 500.
type HandlerFunc func(w http.ResponseWriter, r *http.Request) error

func (h HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	err := h(w, r)
	if err == nil {
		return
	}
	var httpErr *Error
	if errors.As(err, &httpErr) {
		for k, v := range httpErr.Headers {
			w.Header().Set(k, v)
		}
		WriteJSON(w, httpErr.Status, map[string]any{"detail": httpErr.Detail})
		return
	}
	log.Printf("internal error on %s %s: %v", r.Method, r.URL.Path, err)
	WriteJSON(w, http.StatusInternalServerError,
		map[string]any{"detail": "Internal Server Error"})
}

// MarshalJSON encodes v without escaping HTML characters, matching
// Python's json.dumps output more closely than encoding/json defaults.
func MarshalJSON(v any) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimRight(buf.Bytes(), "\n"), nil
}

func WriteJSON(w http.ResponseWriter, status int, v any) {
	data, err := MarshalJSON(v)
	if err != nil {
		log.Printf("failed to encode JSON response: %v", err)
		w.WriteHeader(http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(data)
}

// JSON writes v as a 200 JSON response.
func JSON(w http.ResponseWriter, v any) error {
	WriteJSON(w, http.StatusOK, v)
	return nil
}
