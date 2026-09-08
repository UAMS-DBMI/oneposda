#!/usr/bin/perl -w
#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
# Accepts a finished edit: queues its files for import and hands off.
#
# This used to do the whole accept in one process -- walk every compared file,
# import it, then loop over every file in the old timepoint inserting rows one
# at a time, issuing an activity_task_status UPDATE per file. On a large edit
# that is hours of strictly serial work that cannot be resumed if it dies.
#
# Now it only opens the import phase. The per-file import is done by
# EditWorkerLoop.pl replicas claiming pending_import tasks, and the timepoint is
# built by BuildEditTimepointTp.pl in a single INSERT ... SELECT once they are
# done. The state machine and its compare-and-swap gates are unchanged, so the
# accept is still safe to attempt twice.
#
use strict;
use Posda::DB 'Query';
use Posda::BackgroundProcess;
use Posda::EditStateChange;
use JSON;

$| = 1;

my $usage = <<USAGE_END;
ImportEditsTp.pl <?bkgrnd_id?> <activity_id> <sub_invoc_id> <notify>
or
ImportEditsTp.pl -h

Queues every changed file of the edit <sub_invoc_id> for import.

It will only start if the edit is in state "Comparisons Complete"; if not it
finishes with an error. On success the state becomes "Importing Files" and
edit workers import the files. When the last one is imported a worker advances
the state to "Files Imported" and queues BuildEditTimepointTp.pl, which creates
the new activity timepoint and deletes the temporary directory.
USAGE_END

if($#ARGV == 0 && $ARGV[0] eq "-h"){ print $usage; exit }
unless($#ARGV == 3){
  my $num_args = $#ARGV;
  print "Error: wrong number of args ($num_args) vs 3:\n$usage\n";
  die "$usage\n";
}

my($invoc_id, $activity_id, $subproc_invoc_id, $notify) = @ARGV;
my $background = Posda::BackgroundProcess->new($invoc_id, $notify, $activity_id);
print "Entering Background\n";
$background->Daemonize;

sub report_state_failure {
  my($code, $content, $what) = @_;
  $background->WriteToEmail("$what\n");
  $background->WriteToEmail("Code: $code\n");
  if(!defined($content) or $content eq ""){
    $background->WriteToEmail("No Json");
  } else {
    my $stat = eval { decode_json($content) };
    if($stat){
      for my $i (keys %$stat){
        $background->WriteToEmail("$i - $stat->{$i}\n");
      }
    } else {
      $background->WriteToEmail("$content\n");
    }
  }
}

# Claim the edit. Losing this means someone else already accepted or rejected
# it, and we must not touch the files.
my($code, $content) = Posda::EditStateChange::Trans(
  $subproc_invoc_id, "Comparisons Complete", "Importing Files");
unless($code == 200){
  report_state_failure($code, $content, "Failed to lock Edits:");
  $background->Finish("Error - wrong state");
  exit;
}

my $NumEdits = 0;
Query('EditTaskCountInStates')->RunQuery(sub{
  my($row) = @_;
  $NumEdits = $row->[0];
}, sub{}, $subproc_invoc_id, '{compared}');

unless($NumEdits > 0){
  $background->WriteToEmail(
    "No changed files for subprocess_invocation_id $subproc_invoc_id\n");
  # Put the edit back so it can still be rejected and cleaned up.
  Posda::EditStateChange::Trans(
    $subproc_invoc_id, "Importing Files", "Comparisons Complete");
  $background->Finish("Nothing to import");
  exit;
}

############################################################
# One import_event for the whole accept, recorded on the run so that every
# worker files its imports under it. Previously this process did all the
# importing and could just hold the id in a variable.
Query('InsertEditImportEvent')->RunQuery(
  sub{}, sub{}, "ImportEditsTp.pl", "New files in edits $subproc_invoc_id");
my $IeId;
Query('GetImportEventId')->RunQuery(sub{
  my($row) = @_;
  $IeId = $row->[0];
}, sub {});
unless(defined $IeId){
  $background->WriteToEmail("ERROR: couldn't create an import_event\n");
  $background->Finish("Failed - no import event");
  exit;
}
Query('SetEditImportEvent')->RunQuery(sub{}, sub{}, $IeId, $subproc_invoc_id);

############################################################
# Queue every changed file for import. One statement, whatever the file count.
Query('SeedImportTasks')->RunQuery(sub{}, sub{}, $subproc_invoc_id);

$background->WriteToEmail(
  "Queued $NumEdits edited files for import\n" .
  "Import event: $IeId\n" .
  "Subprocess_invocation_id: $subproc_invoc_id\n\n" .
  "Edit workers are importing the files. When they finish, the new activity\n" .
  "timepoint will be built and you will receive another message.\n");
$background->Finish("Queued $NumEdits files for import");
exit;
