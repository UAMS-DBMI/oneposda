#!/usr/bin/perl -w
#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
# Queued/distributed counterpart to BackgroundEditorTp.pl.
#
# Same command line and same STDIN format; the difference is what it does with
# the result. BackgroundEditorTp.pl expands the series into a %SopsToEdit hash
# held in memory for the life of the process, then drives eight child editors
# and one streaming comparer from a select() reactor, and stays resident for the
# whole run. Nothing about that plan is durable, so killing it loses everything
# and strands the temp tree.
#
# This script only plans. It streams one dicom_edit_task row per file into the
# database and exits, which means:
#   - memory is O(1) in the number of files rather than O(all of them),
#   - the work list survives a restart,
#   - EditWorkerLoop.pl replicas can be scaled up and down against it, and
#   - it does not hold a WorkerNode slot for hours.
#
use strict;
use Posda::DB 'Query';
use Posda::BackgroundProcess;
use Posda::EditStateChange;
use Digest::MD5;
use JSON;
use Data::UUID;

our $ug = Data::UUID->new;
sub get_uuid {
  return lc $ug->create_str();
}

$| = 1;

my $usage = <<USAGE_END;
Usage:
BackgroundEditorTpQ.pl <?bkgrnd_id?> <activity_id> "<edit_desciption>" <notify>
or
BackgroundEditorTpQ.pl -h

Expects lines of the form:
<series_instance_uid>&<op>&<tag>&<val1>&<val2>

Input format, tag syntax and the supported edit operations are identical to
BackgroundEditorTp.pl -- see that script's usage message for the full
description. The difference is purely in execution: this version writes the
edits to the dicom_edit_task queue and exits, and EditWorkerLoop.pl workers
perform them. Progress and state live in dicom_edit_compare_disposition and
dicom_edit_task, so the run can be stopped and resumed.

Edited files are written under:
  <POSDA_CACHE_ROOT>/edits/<uuid>/pat_<hash>/studies/series_<hash>/<file_id>.dcm

The pat_/series_ names are short MD5 prefixes of the patient id and series uid
rather than the sequence numbers BackgroundEditorTp.pl used. Sequence counters
only work inside a single process that holds the whole plan in memory; a hash
lets any worker derive the same path, and still keeps ids out of the pathname.
USAGE_END

if($#ARGV == 0 && $ARGV[0] eq "-h"){ print $usage; exit }
if($#ARGV != 3){ print "Wrong args: $usage\n"; die "$usage\n\n" }
my($invoc_id, $activity_id, $description, $notify) = @ARGV;

#############################
# Destination directory for the edited files.
my $sub_dir = get_uuid();
my $CacheDir = $ENV{POSDA_CACHE_ROOT};
unless(defined($CacheDir) && -d $CacheDir){
  # The original only warned here and then fell through to a mkdir that could
  # not succeed, which turned a clear configuration error into a confusing one.
  print "Error: Cache dir (" . (defined $CacheDir ? $CacheDir : "<unset>") .
    ") isn't a directory\n";
  die "POSDA_CACHE_ROOT is not usable";
}
my $EditDir = "$CacheDir/edits";
unless(-d $EditDir){
  unless(mkdir($EditDir) == 1){
    print "Error: can't mkdir $EditDir ($!)";
    die "can't mkdir $EditDir";
  }
}
my $DestDir = "$EditDir/$sub_dir";
if(-e $DestDir) {
  print "Error: Destination dir ($DestDir) already exists\n";
  die "destination exists";
}
unless(mkdir($DestDir) == 1){
  print "Error: can't mkdir $DestDir ($!)";
  die "can't mkdir $DestDir";
}

#############################
# Queries
my $get_list_of_sops_and_files = Query("GetFilesAndSopsBySeriesAndTP");
my $look_up_tag = Query("LookUpTag");
my $insert_task = Query("InsertEditTask");

my $current_timepoint_id;
Query("LatestActivityTimepointForActivity")->RunQuery(sub{
  my($row) = @_;
  $current_timepoint_id = $row->[0];
}, sub {}, $activity_id);
unless(defined $current_timepoint_id){
  die "No latest timepoint found for activity $activity_id";
}

# The disposition row is created before any task is inserted, and deliberately
# left in its initial 'Starting Up' state until planning finishes.
# ActiveEditInvocations ignores that state, so no worker can see -- and drain,
# and declare complete -- a task list that is still being written.
Query("CreateDicomEditCompareDisposition")
  ->RunQuery(sub {}, sub{}, $invoc_id, $$, $DestDir);

# Created before planning rather than after, for two reasons: the activity
# status is visible while a large plan is being built, and the rows it writes
# (activity_task_status, background_subprocess) are where a worker later reads
# the run's activity and notify target from, via EditRunContext.
my $background = Posda::BackgroundProcess->new($invoc_id, $notify, $activity_id);
$background->SetActivityStatus("Planning edits");

my $num_tasks = 0;
my $last_line_was_series = 0;
my $last_line_was_edit = 0;
my $accumulating_series = [];
my $current_series = [];
my $accumulating_edits = [];

sub fail_planning {
  my($message) = @_;
  print "$message\n";
  die $message;
}

# pat_<hash> / series_<hash>: stable, derivable by any process, and no ids in
# the path. The originals were in-memory counters ($pat_seq, $series_seq).
sub nickname {
  my($prefix, $value) = @_;
  my $ctx = Digest::MD5->new;
  $ctx->add(defined $value ? $value : "");
  return $prefix . "_" . substr($ctx->hexdigest, 0, 8);
}

#############################
## Expand one series into tasks and stream them into the queue.
sub InsertTasksForSeries {
  my($series, $spec_json) = @_;
  my $found = 0;
  $get_list_of_sops_and_files->RunQuery(sub{
    my($row) = @_;
    my($pat_id, $study_id, $series_id, $sop, $file_id, $path) = @$row;
    $found += 1;
    my $to_path = "$DestDir/" . nickname("pat", $pat_id) .
      "/studies/" . nickname("series", $series_id) . "/$file_id.dcm";
    # The unique index on (subprocess_invocation_id, sop_instance_uid) is what
    # detects a SOP that appeared in an earlier series; no rows back means it
    # was already claimed by a previous insert. This replaces the %SopsToEdit
    # membership test, and is why the planner needs no per-SOP memory.
    my $rows = $insert_task->FetchResults(
      $invoc_id, $sop, $file_id, $path, $to_path, $spec_json);
    unless(defined($rows) && ref($rows) eq "ARRAY" && $#{$rows} >= 0){
      fail_planning("Error: the sop ($sop)\n  occurring in series($series)\n  " .
        "seems to have occurred also in an earlier series");
    }
    $num_tasks += 1;
    unless($num_tasks % 1000){
      $background->SetActivityStatus("Planning: $num_tasks edits queued");
    }
  }, sub {}, $series, $current_timepoint_id);
  return $found;
}

#############################
## Process a list of Edits with series list
sub ProcessEndOfEdits{
  # The edits apply to every series in the group, so process them once and
  # reuse the encoded spec for every task.
  my @processed;
  for my $edit (@$accumulating_edits){
    push @processed, ProcessIndividualEdit($edit);
  }
  my $spec_json = encode_json({ edits => \@processed });
  for my $series (@$current_series){
    InsertTasksForSeries($series, $spec_json);
  }
  $current_series = [];
  $accumulating_edits = [];
}

sub ProcessIndividualEdit{
  my($edit) = @_;
  my $supported_edit_ops = {
    shift_date => 1,
    shift_date_by_year => 1,
    copy_date_from_tag_to_dt => 1,
    copy_from_tag => 1,
    delete_tag => 1,
    set_tag => 1,
    substitute => 1,
    string_replace => 1,
    empty_tag => 1,
    short_hash => 1,
    hash_unhashed_uid => 1,
    date_difference => 1,
    delete_matching_group => 1,
    move_owner_block => 1,
    annotate_img => 1,
    add_tag_to_seq => 1,
  };
  my($op, $tag, $v1, $v2) = @$edit;
  unless(exists $supported_edit_ops->{$op}){
    print "Operation ($op) not supported\n";
    exit;
  }
  $tag = unmetaquote($tag);
  $v1 = unmetaquote($v1);
  $v2 = unmetaquote($v2);
  if($tag =~ /^[A-Za-z]*$/){
    my $tags;
    $look_up_tag->RunQuery(sub {
      my($row) = @_;
      my($tags1, $name, $keyword, $vr, $vm, $is_retired, $comments) = @$row;
      $tags = $tags1;
    }, sub {}, $tag, $tag);
    unless(defined $tags){
      print "Error: Can't identify $tag\n";
      exit;
    }
    $tag = $tags;
  }
  my $tag_mode = "exact";
  my $check_item_at_end = 0;
  if($tag =~ /\[\d+\]$/){
    $tag_mode = "item";
    $check_item_at_end = 1;
  }
  if($tag =~ /^\.\.(\(....,....\))$/) {
    $tag = $1;
    $tag_mode = "leaf";
  }
  if($tag =~ /</){
    $tag_mode = "pattern";
  }
  if($tag =~ /^\.\.(\(....,\"[^\"]*\",..\))$/) {
    $tag = $1;
    $tag_mode = "leaf";
  }
#  if(look_for_private($tag)){
#    print "Error: Private reference ($tag) not supported\n";
#    exit;
#  }
  if($tag eq "60xx" || $tag eq "50xx"){
    $tag_mode = "group_pattern";
  }
  if($tag =~ /^\([0-9a-f][0-9a-f][0-9a-f][13579bdf]$/){
    $tag_mode = "private_group";
  }
#  if($tag =~ /x/){
#    print "Error: repeating element <$tag> not supported\n";
#    exit;
#  }

  if($check_item_at_end && $tag_mode ne "item"){
    print "Error: Bad item specification: $tag\n";
    exit;
  }
  if($tag_mode eq "exact"){
    if($tag =~ /^\(.*\)$/){
      #OK
    } else {
      if($tag =~ /^....,....$/){
        print "tag $tag doesn't have enclosing parens\n";
        exit;
      }
    }
  }
  return {op => $op, tag =>$tag, tag_mode => $tag_mode, arg1 => $v1,
    arg2 =>  $v2};
}

sub unmetaquote{
  my($v) = @_;
  if($v =~ /^<(.*)>$/) { $v = $1 }
  elsif($v =~ /^'<(.*)>$/) { $v = $1 }
  return $v;
}

#############################
# Planning either finishes and hands the run to the workers, or it must leave
# the disposition in a state no worker will touch. ProcessIndividualEdit
# reports bad input by calling exit() directly, which eval cannot intercept, so
# the guarantee is enforced in an END block that covers every exit path.
my $Planned = 0;
END {
  if(defined($invoc_id) && !$Planned){
    Posda::EditStateChange::Trans($invoc_id, "Starting Up", "Planning Failed");
  }
}

#############################
## Parse the input. This state machine is unchanged from BackgroundEditorTp.pl:
## series lines accumulate, the first operation line freezes that accumulation
## into the current group, and a blank or new series line closes the group.
line:
while(my $line = <STDIN>){
  chomp $line;
  my($series_uid, $op, $tag, $v1, $v2) =
    split(/&/, $line);
  if($series_uid){
    if($op) {
      print "Error: operation ($op) on same line as series ($series_uid)\n";
      exit;
    }
    if($last_line_was_edit){
      ProcessEndOfEdits();
    }
    push @$accumulating_series, $series_uid;
    $last_line_was_series = 1;
    next line;
  }
  if($op){
    if($last_line_was_series) {
      $current_series = $accumulating_series;
      $accumulating_series = [];
      unless($#{$current_series} >= 0){
        print "Error: operation($op) applies to no series\n";
        exit;
      }
    }
    push(@{$accumulating_edits}, [$op, $tag, $v1, $v2]);
    $last_line_was_series = 0;
    $last_line_was_edit = 1;
  } elsif ($last_line_was_edit){
    ProcessEndOfEdits();
    $last_line_was_edit = 0;
  }
}
if($last_line_was_edit) { ProcessEndOfEdits(); }

unless($num_tasks > 0){
  print "No sops found to edit\n";
  die "No sops found to edit";
}

#############################
# Hand the run to the workers. Only now does ActiveEditInvocations see it.
my($code, $content) = Posda::EditStateChange::Trans(
  $invoc_id, "Starting Up", "Edits Planned");
unless($code == 200){
  print "Failed to advance state \"Starting Up\" => \"Edits Planned\"\n";
  print "Code: $code\n";
  print "$content\n" if $content;
  die "state transition failed";
}
$Planned = 1;

Query("UpdateEditProgressCounts")->RunQuery(sub {}, sub {},
  $num_tasks, 0, 0, $invoc_id);

$background->WriteToEmail(
  "Planned $num_tasks file edits\n" .
  "Description: $description\n" .
  "Results dir: $DestDir\n" .
  "Subprocess_invocation_id: $invoc_id\n\n" .
  "Workers will now perform the edits. You will receive a second message with\n" .
  "the difference reports and the accept/reject buttons when they finish.\n");
$background->Finish("Planned $num_tasks edits");

print "Planned $num_tasks edits\n";
print "Directory: $DestDir\n";
print "Subprocess_invocation_id: $invoc_id\n";
exit;
