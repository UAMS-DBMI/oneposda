package Posda::Passwords;

use Modern::Perl '2010';
use Digest::SHA 'sha256_base64';
use Crypt::Bcrypt qw(bcrypt bcrypt_check);

sub make_salt {
  my ($len) = @_;
  if (not defined $len) {
    $len = 8;  # default length
  }
  my @chars = ('.', '/', 0..9, 'A'..'Z', 'a'..'z');
  my $result;

  while ($len--) {
    $result .= $chars[rand @chars];
  }

  return $result;
}

sub make_bcrypt_salt {
  my $octets = "";
  $octets .= chr(int(rand(256))) for 1..16;
  return $octets;
}

sub encode {
  my ($password) = @_;
  return bcrypt($password, '2b', 12, make_bcrypt_salt());
}

sub _encode {
  my ($salt, $password) = @_;
  return "$salt," . sha256_base64($salt . $password);
}

sub is_valid {
  my ($enc_password, $candidate_password) = @_;

  if ($enc_password =~ /^\$2[abxy]\$/) {
    return bcrypt_check($candidate_password, $enc_password);
  }

  my ($salt, $text) = split(',', $enc_password);

  my $new_text = _encode($salt, $candidate_password);

  if ($enc_password eq $new_text) {
    return 1;
  } else {
    return 0;
  }
}

sub needs_rehash {
  my ($enc_password) = @_;
  return $enc_password !~ /^\$2[abxy]\$/ ? 1 : 0;
}

1;
