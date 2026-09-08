#!/usr/bin/perl -w
#
# The diff itself now lives in Posda::EditCompare so the distributed workers can
# run it concurrently. This script keeps the exact stdin/stdout line protocol
# BackgroundEditorTp.pl speaks, so the existing single-process pipeline is
# unchanged.
#
use strict;
use File::Temp qw/ tempfile /;
use Posda::DB::PosdaFilesQueries;
use Posda::EditCompare;
use Digest::MD5;

my $usage = <<EOF;
StreamingEditCompare.pl <subprocess_invocation_id>
or
StreamingEditCompare.pl -h

Populates dicom_edit_compare table
Expect input lines in following format:
<sop_instance_uid>|<from_file>|<to_file>
EOF

$|=1;

if($#ARGV == 0 && $ARGV[0] eq "-h" ){ die $usage }
unless($#ARGV == 0 ){ die $usage }

my ($invoc_id) = @ARGV;

my $ins = PosdaDB::Queries->GetQueryInstance(
  "InsertIntoDicomEditCompareIdempotent");

# Reports repeat heavily across an edit run -- every file getting the same
# treatment produces the same diff text -- so cache the imported file_id by
# report digest. Correctness does not depend on this cache: file.digest is
# unique and the importer resolves an existing digest to the same file_id,
# which is why several workers can now do this concurrently.
my %FileIdByDig;

sub import_report {
  my($text) = @_;
  my $ctx = Digest::MD5->new;
  $ctx->add($text);
  my $dig = $ctx->hexdigest;
  return $FileIdByDig{$dig} if exists $FileIdByDig{$dig};

  my($fh, $path) = tempfile();
  $fh->print($text);
  my $cmd = "ImportSingleFileIntoPosdaAndReturnId.pl \"$path\" " .
    "\"Difference report\"";
  my $result = `$cmd`;
  unlink $path;
  if($result =~ /File id: (.*)/){
    my $file_id = $1;
    $FileIdByDig{$dig} = $file_id;
    return $file_id;
  }
  return undef;
}

line:
while(my $line = <STDIN>){
  chomp $line;
  my($sop_inst, $from_file, $to_file) = split(/\|/, $line);

  my $r = Posda::EditCompare::compare($from_file, $to_file);

  if($r->{Status} eq "Error"){
    print "Failed: $sop_inst|$r->{message}\n";
    next line;
  }
  if($r->{Status} eq "Unchanged"){
    # Reported exactly as before so the caller's counters are unaffected.
    print "Failed: $sop_inst|$r->{message}\n";
    next line;
  }

  my $s_rept_file_id = import_report($r->{short_report});
  unless(defined $s_rept_file_id){
    print "Failed: $sop_inst|Couldn't import short_rept into posda\n";
    next line;
  }
  my $l_rept_file_id = import_report($r->{long_report});
  unless(defined $l_rept_file_id){
    print "Failed: $sop_inst|Couldn't import long_rept into posda\n";
    next line;
  }

  $ins->RunQuery(sub{}, sub{},
    $invoc_id, $r->{from_digest}, $r->{to_digest},
    $s_rept_file_id, $l_rept_file_id, $to_file);
  print "Completed: $sop_inst|$from_file|" .
    "$to_file|$s_rept_file_id|$l_rept_file_id\n";
}
