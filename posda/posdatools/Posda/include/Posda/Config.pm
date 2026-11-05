package Posda::Config;

require Exporter;
@ISA = 'Exporter';
@EXPORT_OK = ('Config', 'Database', 'DatabaseName', 'SubAppUrlPath');

use Modern::Perl '2010';

use Env;
use JSON;

use Posda::DicomSendLocations;
use Posda::DatabaseConfig;

our $vars = {};

# special complex rules for certain config variables
my $loading_rules = {
  dicom_send_locations => sub {
    return Posda::DicomSendLocations::get();
  },
  databases => sub {
    return Posda::DatabaseConfig::get();
  },
  extraction_mgr_port => sub {
    return Config("port") + 2;
  },
  # Number of ports reserved for sub-application (per-session) processes.
  # Overridable with POSDA_APP_PORT_COUNT; nginx must be able to reach every
  # port in the resulting pool (see SubAppUrlPath below).
  app_port_count => sub {
    my $count = $ENV{POSDA_APP_PORT_COUNT};
    return (defined $count && $count =~ /^\d+$/ && $count > 0) ? $count : 16;
  },
  port_pool => sub {
    my $main_port = Config("port");
    my $first = $main_port + 5;
    my $last = $first + Config("app_port_count") - 1;
    return [$first..$last];
  },
};

# URL path prefix (no leading slash) under which nginx proxies a
# sub-application listening on $port. nginx matches it with a single
# regex location, so the pool can grow without touching the proxy config:
#
#   location ~ ^/pa/(646\d\d)/(.*)$ { proxy_pass http://posda:$1/$2$is_args$args; }
sub SubAppUrlPath {
  my ($port) = @_;
  return "pa/$port";
}

sub _get {
  my ($var) = @_;
  my $var_name = "POSDA_$var";

  if (defined $ENV{$var_name}) {
    return $ENV{$var_name};
  } else {
    say STDERR "Attempted to load environment variable $var_name but it was " .
               "not found! Is the Posda environment configured?";
    return undef;
  }
}

sub _load {
  my ($var) = @_;
  if (defined $loading_rules->{$var}) {
    return $loading_rules->{$var}();
  }

  # default rule
  return _get(uc($var));
}

sub Config {
  my ($var) = @_;
  if (not defined $vars->{$var}) {
    $vars->{$var} = _load($var);
  }
  return $vars->{$var};
}

my $driver_map = { postgres => 'Pg',
                   mysql => 'mysql', };

sub Database {
  my ($name) = @_;
  my $db_info = Config('databases')->{$name};

  if (not defined $db_info) {
    say STDERR "Invalid database name requested: $name";
    return 'invalid database name';
  }

  my $driver = $driver_map->{$db_info->{driver}};

  if (not defined $driver) {
    say STDERR "Invalid driver specified in database config: $db_info->{driver}";
    return 'invalid database driver';
  }

  my $prefix = "dbi:$driver:";

  my @params;
  for my $k (keys %$db_info) {
    if ($k ne 'driver' and $k ne 'init' and $k ne 'reset') {
      push @params, "$k=$db_info->{$k}";
    }
  }

  return $prefix . join(';', @params);
}

sub DatabaseName {
  my ($name) = @_;
  my $db_info = Config('databases')->{$name};
  return $db_info->{database};
}

1;
