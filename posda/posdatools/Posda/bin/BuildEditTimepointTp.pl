#!/usr/bin/perl -w
#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
# Final stage of accepting an edit: build the new activity timepoint and clean
# up the temporary directory.
#
# Queued by whichever edit worker imports the last file. The timepoint itself is
# one INSERT ... SELECT rather than the per-file Perl loop ImportEditsTp.pl used
# to run, which also issued an activity_task_status UPDATE for every file in the
# timepoint -- two round trips per file to copy a list that the database can
# copy by itself.
#
use strict;
use Posda::DB 'Query';
use Posda::BackgroundProcess;
use Posda::EditStateChange;
use File::Path qw( rmtree );
use JSON;

$| = 1;

my $usage = <<USAGE_END;
BuildEditTimepointTp.pl <?bkgrnd_id?> <activity_id> <sub_invoc_id> <notify>
or
BuildEditTimepointTp.pl -h

Creates the new activity timepoint for the accepted edit <sub_invoc_id>,
substituting each edited file for the file it was edited from and carrying
every other file across unchanged, then removes the temporary directory.

Requires the edit to be in state "Files Imported".
USAGE_END

if($#ARGV == 0 && $ARGV[0] eq "-h"){ print $usage; exit }
unless($#ARGV == 3){
  print "Error: wrong number of args\n$usage\n";
  die "$usage\n";
}
my($invoc_id, $activity_id, $subproc_invoc_id, $notify) = @ARGV;

my $background = Posda::BackgroundProcess->new($invoc_id, $notify, $activity_id);
$background->Daemonize;
my $Start = time;

sub report_state_failure {
  my($code, $content, $what) = @_;
  $background->WriteToEmail("$what\n");
  $background->WriteToEmail("Code: $code\n");
  if(!defined($content) or $content eq ""){
    $background->WriteToEmail("No Json");
  } else {
    my $stat = eval { decode_json($content) };
    if($stat){
      for my $i (keys %$stat){ $background->WriteToEmail("$i - $stat->{$i}\n") }
    } else {
      $background->WriteToEmail("$content\n");
    }
  }
}

my($code, $content) = Posda::EditStateChange::Trans(
  $subproc_invoc_id, "Files Imported", "Building Timepoint");
unless($code == 200){
  report_state_failure($code, $content,
    "Failed to advance state \"Files Imported\" => \"Building Timepoint\":");
  $background->Finish("Error - wrong state");
  exit;
}

my $OldActivityTimepoint;
Query('LatestActivityTimepointForActivity')->RunQuery(sub{
  my($row) = @_;
  $OldActivityTimepoint = $row->[0];
}, sub {}, $activity_id);
unless(defined $OldActivityTimepoint){
  $background->WriteToEmail(
    "ERROR: no latest timepoint found for activity $activity_id\n");
  $background->Finish("Failed - no timepoint");
  exit;
}

my $atp_com = "New Timepoint for ImportedEdits $subproc_invoc_id";
Query("CreateActivityTimepoint")->RunQuery(sub {}, sub {},
  $activity_id, $0, $atp_com, $notify);
my $NewTp;
Query("GetActivityTimepointId")->RunQuery(sub {
  my($row) = @_;
  $NewTp = $row->[0];
}, sub{});
unless(defined $NewTp){
  $background->WriteToEmail(
    "ERROR: Unable to get new activity timepoint id.\n");
  $background->Finish("Failed - check report");
  exit;
}

$background->SetActivityStatus(
  "Building timepoint ($OldActivityTimepoint -> $NewTp)");
$background->WriteToEmail(
  "Building timepoint: ($OldActivityTimepoint -> $NewTp)\n");

# The whole timepoint, in one statement.
Query("BuildTimepointFromEditTasks")->RunQuery(sub {}, sub {},
  $NewTp, $subproc_invoc_id, $OldActivityTimepoint);

my $n_total = 0;
Query('FilesInTimepoint')->RunQuery(sub { $n_total += 1 }, sub{}, $NewTp);
my $n_new = 0;
Query('EditTaskCountInStates')->RunQuery(sub{
  my($row) = @_;
  $n_new = $row->[0];
}, sub{}, $subproc_invoc_id, '{imported}');

# Edited files whose source was not in the timepoint we replaced. The old code
# found these by deleting from a hash as it walked the timepoint; it is an
# anti-join, and it does not need the whole conversion map in memory.
my $n_orphans = 0;
my $orphan_rpt;
Query('OrphanToFilesForEdit')->RunQuery(sub {
  my($row) = @_;
  my($to_file_id, $from_file_id, $sop) = @$row;
  unless($n_orphans){
    $orphan_rpt = $background->CreateReport("Orphan To Files");
    $orphan_rpt->print("to_file_id,from_file_id,sop_instance_uid\r\n");
  }
  $n_orphans += 1;
  $orphan_rpt->print("$to_file_id,$from_file_id,$sop\r\n");
}, sub{}, $subproc_invoc_id, $OldActivityTimepoint);

($code, $content) = Posda::EditStateChange::Trans(
  $subproc_invoc_id, "Building Timepoint", "Timepoint Created");
unless($code == 200){
  report_state_failure($code, $content,
    "Failed to advance state \"Building Timepoint\" => \"Timepoint Created\":");
  $background->Finish("Error - wrong state");
  exit;
}

#############################
# Clean up the temp tree. The edited files were unlinked as they were imported,
# so this is almost entirely empty directories.
my $dest_dir;
Query('GetEditImportEvent')->RunQuery(sub {
  my($row) = @_;
  $dest_dir = $row->[1];
}, sub {}, $subproc_invoc_id);

my $deleted = "not attempted";
if(defined($dest_dir) && length($dest_dir) && -d $dest_dir){
  # Guard against ever being pointed at something that is not an edit temp dir.
  if($dest_dir =~ m{/edits/[0-9a-f-]{36}/?$}){
    eval { rmtree($dest_dir) };
    $deleted = $@ ? "failed: $@" : "deleted";
  } else {
    $deleted = "refused: $dest_dir does not look like an edit temp directory";
  }
} elsif(defined $dest_dir) {
  $deleted = "already gone";
}
Posda::EditStateChange::Trans(
  $subproc_invoc_id, "Timepoint Created", "Import Complete");

my $elapsed = time - $Start;
my $tt_text = "($OldActivityTimepoint -> $NewTp)";
$background->WriteToEmail(
  "Finished Import $tt_text\n" .
  "  files in new timepoint: $n_total\n" .
  "  edited files:           $n_new\n" .
  "  orphaned edited files:  $n_orphans\n" .
  "  temporary directory:    $deleted\n" .
  "  elapsed:                $elapsed seconds\n");
if($n_orphans > 0){
  $background->WriteToEmail(
    "\n$n_orphans edited files were produced from files that were not in\n" .
    "timepoint $OldActivityTimepoint. See the \"Orphan To Files\" report.\n");
}

$background->Finish(
  "Done $tt_text (new: $n_new, total: $n_total, orphans: $n_orphans) " .
  "($elapsed elapsed)");
exit;
