// Package auth implements login tokens (stored in redis, like the
// Python implementation) and the request middleware that resolves the
// current user.
package auth

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"

	"tcia/posda-api/internal/db"
	"tcia/posda-api/internal/httpx"
)

// TokenExpire matches the Python TOKEN_EXPIRE of 1 hour; tokens are
// re-extended on every authenticated request.
const TokenExpire = time.Hour

type User struct {
	UserID   int64   `json:"user_id"`
	Username string  `json:"username"`
	FullName *string `json:"full_name"`
	Disabled *bool   `json:"disabled"`

	hashedPassword string
}

type Service struct {
	DB          *db.DB
	Redis       *redis.Client
	SystemToken string
}

func NewService(database *db.DB, redisHost, systemToken string) *Service {
	return &Service{
		DB: database,
		// Login tokens live in redis db 1, separate from other data.
		Redis:       redis.NewClient(&redis.Options{Addr: redisHost + ":6379", DB: 1}),
		SystemToken: systemToken,
	}
}

func (s *Service) userFromDatabase(ctx context.Context, username string) (*User, error) {
	row, found, err := s.DB.FetchOne(ctx, `
        select
            user_id,
            user_name as username,
            full_name,
            password as hashed_password,
            disabled
        from auth.users
        where user_name = $1
    `, username)
	if err != nil || !found {
		return nil, err
	}

	u := &User{
		UserID:         row.GetInt("user_id"),
		Username:       row.GetString("username"),
		hashedPassword: row.GetString("hashed_password"),
	}
	if v, ok := row.Get("full_name").(string); ok {
		u.FullName = &v
	}
	if v, ok := row.Get("disabled").(bool); ok {
		u.Disabled = &v
	}
	return u, nil
}

// decodeToken resolves a token to a user. The system token is checked
// before redis so it works even when redis is unavailable.
func (s *Service) decodeToken(ctx context.Context, token string) (*User, error) {
	if token == "" {
		return nil, nil
	}
	if token == s.SystemToken {
		return s.userFromDatabase(ctx, "system")
	}

	username, err := s.Redis.Get(ctx, token).Result()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return nil, nil
		}
		log.Printf("redis error while resolving token: %v", err)
		return nil, nil
	}
	s.Redis.Expire(ctx, token, TokenExpire)

	return s.userFromDatabase(ctx, username)
}

// requestToken extracts the login token from the Authorization header,
// falling back to the "logintoken" cookie like the Python version.
func requestToken(r *http.Request) string {
	authz := r.Header.Get("Authorization")
	if scheme, token, found := strings.Cut(authz, " "); found &&
		strings.EqualFold(scheme, "Bearer") {
		return strings.TrimSpace(token)
	}
	if c, err := r.Cookie("logintoken"); err == nil {
		return c.Value
	}
	return ""
}

type contextKey struct{}

// CurrentUser returns the logged-in user placed in the request context
// by Middleware. It is nil on unauthenticated routes.
func CurrentUser(r *http.Request) *User {
	u, _ := r.Context().Value(contextKey{}).(*User)
	return u
}

var errNotAuthenticated = &httpx.Error{
	Status:  http.StatusUnauthorized,
	Detail:  "Invalid authentication credentials",
	Headers: map[string]string{"WWW-Authenticate": "Bearer"},
}

// Middleware enforces login and stores the active user in the request
// context (equivalent to Depends(get_current_active_user)).
func (s *Service) Middleware(next httpx.HandlerFunc) httpx.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		user, err := s.decodeToken(r.Context(), requestToken(r))
		if err != nil {
			return err
		}
		if user == nil {
			return errNotAuthenticated
		}
		if user.Disabled != nil && *user.Disabled {
			return httpx.NewError(http.StatusBadRequest, "Inactive user")
		}
		ctx := context.WithValue(r.Context(), contextKey{}, user)
		return next(w, r.WithContext(ctx))
	}
}

// Login implements POST /auth/token: it verifies the posted form
// credentials and returns a fresh bearer token stored in redis.
func (s *Service) Login(w http.ResponseWriter, r *http.Request) error {
	if err := r.ParseForm(); err != nil {
		return httpx.NewError(http.StatusBadRequest, "invalid form data")
	}
	username := r.PostFormValue("username")
	password := r.PostFormValue("password")

	user, err := s.userFromDatabase(r.Context(), username)
	if err != nil {
		return err
	}
	if user == nil || !PasswordIsValid(user.hashedPassword, password) {
		return httpx.NewError(http.StatusBadRequest, "Incorrect username or password")
	}

	token := newUUID4()
	if err := s.Redis.Set(r.Context(), token, user.Username, TokenExpire).Err(); err != nil {
		return err
	}

	return httpx.JSON(w, map[string]any{
		"access_token": token,
		"token_type":   "bearer",
	})
}

// newUUID4 generates a random RFC 4122 version-4 UUID string.
func newUUID4() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(err) // crypto/rand failure is unrecoverable
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}
