#!/usr/bin/perl -w
#
# PosdaIngestRtBridge - run RT module handlers on behalf of the Python
# ingest pipeline.
#
# The Python port of the fast file processor handles every SOP class itself
# except the three RT ones, whose handlers depend on Posda::Dataset's
# sequence navigation (the "(3006,0010)[<0>](3006,00c0)" signature form).
# Rather than port that machinery up front, Python runs the leading non-RT
# handlers and hands the trailing RT block to this script.
#
# That split is safe because in all three RT SOP classes the RT handlers are
# a contiguous trailing block, and the only value they read from the shared
# $hist that Python produces is image_id (used by RTDose).
#
# Protocol: one JSON request on stdin, one JSON response on stdout.
#
#   request:  {"file_id":1,"path":"/x.dcm","handlers":["RTDose","RTDvh"],
#              "hist":{"image_id":45}}
#   response: {"errors":["..."],"hist":{...}}
#
# Errors are returned rather than written here: the Python side owns the
# dicom_process_errors flush so that all of a file's complaints are written
# in one place, in the Perl's original order.
#
use strict;
use warnings;

use JSON;
use DBD::Pg;
use Posda::Config ('Database', 'Config');
use Posda::NewTry;
use Posda::Dataset;
use Posda::DB::Modules;

# Posda::Config::Database only recognises names listed in
# Config/databases.json, so the differential harness -- which runs against a
# throwaway copy of the schema -- builds the DSN directly. Both forms are
# equivalent for posda_files: the JSON entry carries only a database name and
# driver, and host/user/password come from the libpq environment.
my $DSN =
  exists $ENV{POSDA_INGEST_DB}
  ? "dbi:Pg:database=$ENV{POSDA_INGEST_DB}"
  : Database('posda_files');

my $HANDLERS = {
  StructureSet      => \&Posda::DB::Modules::StructureSet,
  RoiContour        => \&Posda::DB::Modules::RoiContour,
  RtRoiObservations => \&Posda::DB::Modules::RtRoiObservations,
  RtPlan            => \&Posda::DB::Modules::RtPlan,
  RtPrescription    => \&Posda::DB::Modules::RtPrescription,
  RtToleranceTables => \&Posda::DB::Modules::RtToleranceTables,
  RtPatientSetup    => \&Posda::DB::Modules::RtPatientSetup,
  RtFractionScheme  => \&Posda::DB::Modules::RtFractionScheme,
  RtBeams           => \&Posda::DB::Modules::RtBeams,
  RtBrachy          => \&Posda::DB::Modules::RtBrachy,
  RTDose            => \&Posda::DB::Modules::RTDose,
  RTDvh             => \&Posda::DB::Modules::RTDvh,
};

$| = 1;

my $input = do { local $/; <STDIN> };
my $request = decode_json($input);

my @errors;
my $response = { errors => \@errors };

my $db = DBI->connect($DSN);
unless ($db) {
  print encode_json({ errors => ["rt_bridge: couldn't connect to $DSN"],
                      fatal => 1 }), "\n";
  exit 1;
}

my $try = Posda::NewTry->new($request->{path});
unless (exists $try->{dataset}) {
  print encode_json({
    errors => ["rt_bridge: $request->{path} didn't parse"],
    fatal  => 1,
  }), "\n";
  $db->disconnect;
  exit 1;
}

# Seed $hist with whatever the Python handlers published. image_id is the
# only key the RT handlers read from outside their own group, but passing
# the dict wholesale keeps this robust if that changes.
my $hist = $request->{hist} || {};

for my $name (@{ $request->{handlers} }) {
  my $handler = $HANDLERS->{$name};
  unless ($handler) {
    push @errors, "rt_bridge: no such handler \"$name\"";
    next;
  }
  eval {
    &$handler($db, $try->{dataset}, $request->{file_id}, $hist, \@errors);
    1;
  } or do {
    my $error = $@ || 'unknown error';
    chomp $error;
    push @errors, "rt_bridge: $name died: $error";
  };
}

$db->disconnect;

# Only scalar hist entries survive the round trip; the nested structures
# (roi, ss_for_by_item) are internal to one file's RT handlers.
my %out_hist;
for my $key (keys %$hist) {
  my $value = $hist->{$key};
  $out_hist{$key} = $value unless ref $value;
}
$response->{hist} = \%out_hist;

print encode_json($response), "\n";
