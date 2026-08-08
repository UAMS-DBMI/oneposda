package auth

import "testing"

// Vectors from the Python password.py self-test (which itself matches
// the Perl Passwords.pm implementation).
func TestEncodeWithSaltMatchesPerl(t *testing.T) {
	got := encodeWithSalt("aJE5lY8D", "admin")
	want := "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE"
	if got != want {
		t.Errorf("encodeWithSalt = %q, want %q", got, want)
	}
}

func TestPasswordIsValid(t *testing.T) {
	hashed := "aJE5lY8D,2wUueoiymAn8HsfbdAp0kPfTiODV7kpeNUttYTgQGbE"
	if !PasswordIsValid(hashed, "admin") {
		t.Error("expected password 'admin' to validate")
	}
	if PasswordIsValid(hashed, "wrong") {
		t.Error("expected password 'wrong' to fail")
	}
	if PasswordIsValid("garbage-no-comma", "admin") {
		t.Error("expected malformed hash to fail")
	}
}

func TestMakeSaltLength(t *testing.T) {
	for _, n := range []int{3, 8, 9} {
		if got := len(MakeSalt(n)); got != n {
			t.Errorf("MakeSalt(%d) length = %d", n, got)
		}
	}
}

func TestFreshEncodeRoundTrip(t *testing.T) {
	hashed := EncodePassword("some test")
	if !PasswordIsValid(hashed, "some test") {
		t.Error("freshly encoded password should validate")
	}
}
