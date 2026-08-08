package auth

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"math/big"
	"strings"
)

// saltChars matches the Perl/Python implementations: '.', '/', digits,
// then ASCII letters.
const saltChars = "./0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

// MakeSalt returns a random salt of the given length.
func MakeSalt(length int) string {
	var b strings.Builder
	max := big.NewInt(int64(len(saltChars)))
	for range length {
		n, err := rand.Int(rand.Reader, max)
		if err != nil {
			panic(err) // crypto/rand failure is unrecoverable
		}
		b.WriteByte(saltChars[n.Int64()])
	}
	return b.String()
}

// EncodePassword hashes a password with a fresh 8-character salt,
// producing the "salt,digest" format stored in auth.users.
func EncodePassword(password string) string {
	return encodeWithSalt(MakeSalt(8), password)
}

// encodeWithSalt mirrors Passwords.pm: base64(sha256(salt + password))
// with base64 padding stripped for Perl compatibility.
func encodeWithSalt(salt, password string) string {
	sum := sha256.Sum256([]byte(salt + password))
	digest := base64.StdEncoding.EncodeToString(sum[:])
	digest = strings.ReplaceAll(digest, "=", "")
	return salt + "," + digest
}

// PasswordIsValid checks a candidate password against a stored
// "salt,digest" hash.
func PasswordIsValid(hashed, candidate string) bool {
	salt, _, found := strings.Cut(hashed, ",")
	if !found {
		return false
	}
	return encodeWithSalt(salt, candidate) == hashed
}
