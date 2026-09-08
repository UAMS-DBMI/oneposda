#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
use strict;
package Posda::EditCompare;

# The from/to DICOM diff, lifted out of StreamingEditCompare.pl.
#
# The original was a single long-lived process for an entire edit run, fed one
# line at a time down a pipe, which made it the throughput ceiling of the whole
# pipeline and meant a kill lost every comparison in flight. Pulling the diff
# into a module lets any number of workers run it concurrently.
#
# This deliberately does NOT import the reports or write dicom_edit_compare.
# Callers differ in how they do that: StreamingEditCompare.pl shells out to
# ImportSingleFileIntoPosdaAndReturnId.pl, while EditWorkerLoop.pl calls
# Posda::File::Import::insert_file in-process. Keeping the diff pure also makes
# it safe to run redundantly, which is what happens when a task is reclaimed.

use Posda::Try;
use Posda::DiffDicom;
use Posda::Dataset;

require Exporter;
our @ISA = ( 'Exporter' );
our @EXPORT_OK = ( 'compare' );

# compare($from_file, $to_file) -> result hashref
#
#   { Status => "OK",        from_digest, to_digest, short_report, long_report }
#   { Status => "Unchanged", from_digest, to_digest, message }
#   { Status => "Error",     message }
#
# "Unchanged" is the empty-diff case: the edit ran but altered nothing. The old
# code reported that as "Failed: <sop>|no lines in short_rept" and counted it
# under "not changed", conflating a file that needed no edit with a file whose
# edit blew up. It gets its own status here so the two can be told apart.
sub compare {
  my($from_file, $to_file) = @_;

  my $f_try;
  eval { $f_try = Posda::Try->new($from_file) };
  if($@){
    return { Status => "Error", message => "$from_file failed to open" };
  }
  unless(exists $f_try->{dataset}){
    return { Status => "Error", message => "$from_file is not a dicom file" };
  }

  my $t_try;
  eval { $t_try = Posda::Try->new($to_file) };
  if($@){
    return { Status => "Error", message => "$to_file failed to open" };
  }
  unless(exists $t_try->{dataset}){
    return { Status => "Error", message => "$to_file is not a dicom file" };
  }

  my $fds   = $f_try->{dataset};
  my $tds   = $t_try->{dataset};
  my $f_dig = $f_try->{digest};
  my $t_dig = $t_try->{digest};

  my($s_rept, $l_rept);
  eval {
    my $diff = Posda::DiffDicom->new($fds, $tds);
    $diff->Analyze;
    my($only_in_from, $only_in_to, $different) = $diff->SemiDiffReport;
    ($s_rept, $l_rept) =
      $diff->ReportFromSemi($only_in_from, $only_in_to, $different);
  };
  if($@){
    return { Status => "Error", message => "diff failed: $@" };
  }

  $s_rept = "" unless defined $s_rept;
  $l_rept = "" unless defined $l_rept;

  if(length($s_rept) <= 0){
    return { Status => "Unchanged", from_digest => $f_dig,
             to_digest => $t_dig, message => "no lines in short_rept" };
  }
  if(length($l_rept) <= 0){
    return { Status => "Unchanged", from_digest => $f_dig,
             to_digest => $t_dig, message => "no lines in long_rept" };
  }

  return {
    Status       => "OK",
    from_digest  => $f_dig,
    to_digest    => $t_dig,
    short_report => $s_rept,
    long_report  => $l_rept,
  };
}

1;
