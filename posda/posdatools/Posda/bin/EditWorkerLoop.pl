#!/usr/bin/perl -w
#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
# A stateless, horizontally scalable worker for the distributed DICOM editor.
#
# Takes no arguments and is told nothing about which edit to work on: it finds
# runnable work itself via ActiveEditInvocations, so a deployment is scaled
# purely by replica count. Every unit of work is one row of dicom_edit_task,
# claimed with FOR UPDATE SKIP LOCKED under a lease.
#
# Being killed is a supported outcome, not an error case:
#
#   SIGTERM  finishes the file in flight, hands back anything claimed but not
#            started, and exits 0. This is the k8s scale-down path.
#   SIGKILL  leaves rows in an *ing state with a lease that expires. The next
#            ClaimEditTasks reclaims them; there is no reaper. Redoing an edit
#            is safe because the engine is deterministic and the output is
#            published by rename(), so a partial file is never visible.
#
use strict;
use Posda::DB 'Query';
use Posda::EditFile;
use Posda::EditCompare;
use Posda::EditStateChange;
use Posda::EnqueueWork;
use Posda::File::Import;
use File::Temp qw( tempfile );
use Digest::MD5;
use Sys::Hostname;
use JSON;
use POSIX ();

$| = 1;

my $usage = <<USAGE_END;
EditWorkerLoop.pl [-h]

Performs queued DICOM edits, comparisons and imports for the distributed
editor. Runs until terminated. Takes no arguments.

Environment:
  POSDA_EDIT_WORKER_BATCH         files claimed per round        (default 4)
  POSDA_EDIT_WORKER_LEASE         lease seconds per claim        (default 1800)
  POSDA_EDIT_WORKER_TIMEOUT       per-file timeout in seconds    (default 600)
  POSDA_EDIT_WORKER_MAX_ATTEMPTS  give up on a file after N tries (default 5)
  POSDA_EDIT_WORKER_IDLE_MIN      idle poll floor in seconds     (default 1)
  POSDA_EDIT_WORKER_IDLE_MAX      idle poll ceiling in seconds   (default 15)
  POSDA_EDIT_WORKER_NAME          identifies this worker in dicom_edit_task
USAGE_END

if($#ARGV == 0 && $ARGV[0] eq "-h"){ print $usage; exit }

sub env_num {
  my($name, $default) = @_;
  my $v = $ENV{$name};
  return $default unless defined($v) && $v =~ /^\d+$/;
  return $v + 0;
}

my $BATCH        = env_num("POSDA_EDIT_WORKER_BATCH", 4);
my $LEASE        = env_num("POSDA_EDIT_WORKER_LEASE", 1800);
my $TIMEOUT      = env_num("POSDA_EDIT_WORKER_TIMEOUT", 600);
my $MAX_ATTEMPTS = env_num("POSDA_EDIT_WORKER_MAX_ATTEMPTS", 5);
my $IDLE_MIN     = env_num("POSDA_EDIT_WORKER_IDLE_MIN", 1);
my $IDLE_MAX     = env_num("POSDA_EDIT_WORKER_IDLE_MAX", 15);
my $WorkerId     = $ENV{POSDA_EDIT_WORKER_NAME} || (hostname() . "-$$");

# The lease has to outlive the work it covers or another worker will reclaim a
# file that is still being edited. A claim covers a whole batch, so the lease is
# refreshed per file as the batch is worked through (see process_batch).
if($TIMEOUT >= $LEASE){
  print STDERR "POSDA_EDIT_WORKER_TIMEOUT ($TIMEOUT) must be less than " .
    "POSDA_EDIT_WORKER_LEASE ($LEASE)\n";
  exit 1;
}

my $ShuttingDown = 0;
$SIG{TERM} = sub { $ShuttingDown = 1 };
$SIG{INT}  = sub { $ShuttingDown = 1 };

print "EditWorkerLoop $WorkerId starting " .
  "(batch=$BATCH lease=${LEASE}s timeout=${TIMEOUT}s)\n";

#############################
# Queries
my $q_active    = Query("ActiveEditInvocations");
my $q_claim     = Query("ClaimEditTasks");
my $q_complete  = Query("CompleteEditTask");
my $q_fail      = Query("FailEditTask");
my $q_release   = Query("ReleaseEditTask");
my $q_extend    = Query("ExtendEditTaskLease");
my $q_counts    = Query("EditTaskStateCounts");
my $q_progress  = Query("UpdateEditProgressCounts");
my $q_compare   = Query("InsertIntoDicomEditCompareIdempotent");
my $q_importev  = Query("GetEditImportEvent");
my $q_context   = Query("EditRunContext");
my $q_fileid    = Query("GetFileIdByDigest");
my $q_import_ok = Query("CompleteImportTask");

#############################
# Run a unit of DICOM work in a forked child.
#
# The child does no database work at all -- it returns its result over a pipe
# and the parent performs every write. That keeps a forked copy of the DBI
# handle from ever touching the socket the parent is using, and it means an
# exception (or a segfault) inside Posda::Dataset costs one file rather than the
# whole worker. The original design got this isolation from exec'ing
# NewSubprocessEditor.pl per file; this keeps the isolation without paying for
# an exec and an interpreter startup every time.
sub run_isolated {
  my($work) = @_;
  my($rd, $wr);
  unless(pipe($rd, $wr)){
    return { Status => "Error", message => "pipe failed: $!" };
  }
  my $pid = fork();
  unless(defined $pid){
    close $rd; close $wr;
    return { Status => "Error", message => "fork failed: $!" };
  }
  if($pid == 0){
    close $rd;
    $SIG{TERM} = 'DEFAULT';
    my $res = eval { $work->() };
    if($@){ $res = { Status => "Error", message => "exception: $@" } }
    unless(ref($res) eq "HASH"){
      $res = { Status => "Error", message => "no result from child" };
    }
    eval { print $wr encode_json($res) };
    close $wr;
    # _exit, not exit: skip global destruction so the inherited DBI handle is
    # not disconnected out from under the parent.
    POSIX::_exit(0);
  }

  close $wr;
  my $json = "";
  my $timed_out = 0;
  eval {
    local $SIG{ALRM} = sub { die "alarm\n" };
    alarm($TIMEOUT);
    local $/;
    $json = <$rd>;
    alarm(0);
  };
  if($@){
    alarm(0);
    $timed_out = 1;
    kill 'KILL', $pid;
  }
  close $rd;
  waitpid($pid, 0);

  if($timed_out){
    return { Status => "Error",
             message => "timed out after ${TIMEOUT}s" };
  }
  unless(defined($json) && length($json)){
    return { Status => "Error",
             message => "worker child died without returning a result" };
  }
  my $res = eval { decode_json($json) };
  if($@ or ref($res) ne "HASH"){
    return { Status => "Error", message => "unparsable child result" };
  }
  return $res;
}

#############################
# Import a diff report and return its file_id.
#
# Reports repeat heavily across a run, so cache by digest. The cache is only an
# optimisation: file.digest is unique and the importer resolves an existing
# digest to the same file_id, which is what makes it safe for many workers to
# import the same report text at the same time.
my %ReportIdByDigest;
sub import_report {
  my($text) = @_;
  my $ctx = Digest::MD5->new;
  $ctx->add($text);
  my $dig = $ctx->hexdigest;
  return $ReportIdByDigest{$dig} if exists $ReportIdByDigest{$dig};

  my($fh, $path) = tempfile();
  print $fh $text;
  close $fh;
  my $resp = Posda::File::Import::insert_file($path, "Difference report");
  unlink $path;
  if($resp->is_error){
    return undef;
  }
  my $id = $resp->file_id;
  # Bound the cache so a very long run cannot grow it without limit.
  %ReportIdByDigest = () if keys(%ReportIdByDigest) > 20000;
  $ReportIdByDigest{$dig} = $id;
  return $id;
}

#############################
# Stage handlers. Each takes the claimed row and returns 1 if it did work.

sub do_edit {
  my($inv, $t) = @_;
  my($task_id, $sop, $from_path, $to_path, $spec_json) =
    @{$t}[0, 1, 2, 3, 4];

  my $spec = eval { decode_json($spec_json) };
  if($@ or ref($spec) ne "HASH"){
    $q_fail->RunQuery(sub{}, sub{}, "edit_failed",
      "unreadable edit_spec: $@", $task_id);
    return 1;
  }

  my $r = run_isolated(sub {
    return Posda::EditFile::apply_edits($from_path, $to_path, $spec);
  });

  if($r->{Status} eq "OK"){
    $q_complete->RunQuery(sub{}, sub{}, "pending_compare",
      $r->{from_digest}, $r->{to_digest}, $task_id);
  } else {
    $q_fail->RunQuery(sub{}, sub{}, "edit_failed",
      $r->{message}, $task_id);
  }
  return 1;
}

sub do_compare {
  my($inv, $t) = @_;
  my($task_id, $sop, $from_path, $to_path) = @{$t}[0, 1, 2, 3];

  my $r = run_isolated(sub {
    return Posda::EditCompare::compare($from_path, $to_path);
  });

  if($r->{Status} eq "Unchanged"){
    # The edit ran but changed nothing. The old pipeline reported this as a
    # failure and lumped it in with real errors; it gets its own state so the
    # two can be told apart, and it is deliberately not imported.
    $q_complete->RunQuery(sub{}, sub{}, "unchanged",
      $r->{from_digest}, $r->{to_digest}, $task_id);
    return 1;
  }
  unless($r->{Status} eq "OK"){
    $q_fail->RunQuery(sub{}, sub{}, "compare_failed",
      $r->{message}, $task_id);
    return 1;
  }

  my $short_id = import_report($r->{short_report});
  my $long_id  = defined($short_id) ? import_report($r->{long_report}) : undef;
  unless(defined($short_id) && defined($long_id)){
    $q_fail->RunQuery(sub{}, sub{}, "compare_failed",
      "couldn't import difference report into posda", $task_id);
    return 1;
  }

  $q_compare->RunQuery(sub{}, sub{}, $inv, $r->{from_digest},
    $r->{to_digest}, $short_id, $long_id, $to_path);
  $q_complete->RunQuery(sub{}, sub{}, "compared",
    $r->{from_digest}, $r->{to_digest}, $task_id);
  return 1;
}

# Cached per invocation: the activity and notify target the run belongs to,
# needed to hand off to the report and timepoint jobs.
my %ContextFor;
sub context_for {
  my($inv) = @_;
  return $ContextFor{$inv} if exists $ContextFor{$inv};
  my $row = $q_context->FetchOneHash($inv);
  $row = {} unless ref($row) eq "HASH";
  # An empty substitution would drop an argument rather than pass an empty one,
  # and the jobs we queue check their argument count, so never hand these on
  # undefined. 'nobody' is the sentinel Posda::Inbox already uses.
  $row->{user_to_notify} = 'nobody'
    unless defined($row->{user_to_notify}) && length($row->{user_to_notify});
  $ContextFor{$inv} = $row;
  return $ContextFor{$inv};
}

# Cached per invocation: the import_event every file of this run is filed under.
my %ImportEventFor;
sub import_event_for {
  my($inv) = @_;
  return $ImportEventFor{$inv} if exists $ImportEventFor{$inv};
  my $row = $q_importev->FetchOneHash($inv);
  $ImportEventFor{$inv} = $row ? $row->{import_event_id} : undef;
  return $ImportEventFor{$inv};
}

sub do_import {
  my($inv, $t) = @_;
  my($task_id, $sop, $from_path, $to_path) = @{$t}[0, 1, 2, 3];
  my $to_digest = $t->[6];

  unless(defined $to_digest){
    $q_fail->RunQuery(sub{}, sub{}, "import_failed",
      "no to_file_digest recorded", $task_id);
    return 1;
  }

  # Resolve by digest first. This is what makes the import idempotent: a file
  # already in Posda -- because a previous attempt imported it, or because some
  # other edit produced identical bytes -- resolves to the same file_id and is
  # not imported twice.
  my $to_file_id;
  $q_fileid->RunQuery(sub {
    my($row) = @_;
    $to_file_id = $row->[0];
  }, sub {}, $to_digest);

  if(defined $to_file_id){
    unlink $to_path if -f $to_path;
  } else {
    unless(-f $to_path){
      $q_fail->RunQuery(sub{}, sub{}, "import_failed",
        "neither file_id nor path exists for to_file $to_digest", $task_id);
      return 1;
    }
    my $resp = Posda::File::Import::insert_file(
      $to_path, "", import_event_for($inv));
    if($resp->is_error){
      $q_fail->RunQuery(sub{}, sub{}, "import_failed",
        "import failed: " . $resp->message, $task_id);
      return 1;
    }
    $to_file_id = $resp->file_id;
    unlink $to_path;
  }

  $q_import_ok->RunQuery(sub{}, sub{}, $to_file_id, $task_id);
  return 1;
}

#############################
# Claim a batch and work through it.
sub process_batch {
  my($inv, $pending_state, $busy_state, $handler) = @_;

  my $rows = $q_claim->FetchResults(
    $busy_state, $WorkerId, $LEASE, $inv, $pending_state, $busy_state, $BATCH);
  return 0 unless defined($rows) && ref($rows) eq "ARRAY" && $#{$rows} >= 0;

  my $done = 0;
  for my $i (0 .. $#{$rows}){
    my $t = $rows->[$i];
    my $task_id = $t->[0];
    my $attempts = $t->[8];

    if($ShuttingDown){
      # Hand back everything not yet started so a scaled-down worker does not
      # make the next one wait out the lease.
      $q_release->RunQuery(sub{}, sub{}, $pending_state, $task_id);
      next;
    }

    # Poison pill: a file that has already failed this many times will fail
    # again, and retrying it forever would keep the run from ever completing.
    if($attempts > $MAX_ATTEMPTS){
      (my $failed = $pending_state) =~ s/^pending_//;
      $failed = ($failed eq "edit") ? "edit_failed"
              : ($failed eq "compare") ? "compare_failed" : "import_failed";
      $q_fail->RunQuery(sub{}, sub{}, $failed,
        "gave up after $attempts attempts", $task_id);
      $done += 1;
      next;
    }

    # The claim leased the whole batch at once, so refresh the rows still ahead
    # of us; each file then starts with a lease that outlives its own timeout.
    for my $j (($i + 1) .. $#{$rows}){
      $q_extend->RunQuery(sub{}, sub{}, $LEASE, $rows->[$j]->[0]);
    }

    $done += $handler->($inv, $t);
  }
  return $done;
}

#############################
# Progress and phase completion.
sub state_counts {
  my($inv) = @_;
  my %c;
  $q_counts->RunQuery(sub {
    my($row) = @_;
    $c{$row->[0]} = $row->[1];
  }, sub {}, $inv);
  return \%c;
}

sub n {
  my($c, @states) = @_;
  my $t = 0;
  for my $s (@states){ $t += ($c->{$s} || 0) }
  return $t;
}

sub update_progress_and_finish {
  my($inv, $disposition) = @_;
  my $c = state_counts($inv);

  my $total     = n($c, qw(pending_edit editing edit_failed pending_compare
                           comparing compared unchanged compare_failed
                           pending_import importing imported import_failed));
  my $changed   = n($c, qw(compared pending_import importing imported
                           import_failed));
  my $unchanged = n($c, qw(unchanged edit_failed compare_failed));

  # Counters only. Writing current_disposition here -- as
  # UpdateDicomEditCompareDisposition does -- would race the transitions below.
  $q_progress->RunQuery(sub{}, sub{}, $total, $changed, $unchanged, $inv);

  my $editing_left = n($c, qw(pending_edit editing pending_compare comparing));
  if($editing_left == 0 &&
     ($disposition eq "Comparisons In Progress" ||
      $disposition eq "Edits Planned")){
    # Exactly one worker wins this compare-and-swap, and that one is
    # responsible for kicking off the reports.
    my($code) = Posda::EditStateChange::Trans(
      $inv, "Comparisons In Progress", "Comparisons Complete");
    if($code == 200){
      print "edit $inv: comparisons complete, queueing reports\n";
      my $ctx = context_for($inv);
      eval {
        Posda::EnqueueWork::enqueue_operation("EditReportsTp", [], undef, {
          activity_id         => $ctx->{activity_id},
          notify              => $ctx->{user_to_notify},
          subprocess_invoc_id => $inv,
        });
      };
      if($@){ print STDERR "edit $inv: couldn't queue reports: $@\n" }
    }
  }

  my $import_left = n($c, qw(pending_import importing));
  if($import_left == 0 && $disposition eq "Importing Files"){
    my($code) = Posda::EditStateChange::Trans(
      $inv, "Importing Files", "Files Imported");
    if($code == 200){
      print "edit $inv: all files imported, queueing timepoint build\n";
      my $ctx = context_for($inv);
      eval {
        Posda::EnqueueWork::enqueue_operation("BuildEditTimepointTp", [], undef, {
          activity_id         => $ctx->{activity_id},
          notify              => $ctx->{user_to_notify},
          subprocess_invoc_id => $inv,
        });
      };
      if($@){ print STDERR "edit $inv: couldn't queue timepoint build: $@\n" }
    }
  }
}

#############################
sub work_on_edit {
  my($inv, $disposition, $num_ready) = @_;
  my $did = 0;

  # A run leaves 'Edits Planned' the moment a worker picks it up. Losing this
  # race is expected and harmless -- another worker got there first.
  if($disposition eq "Edits Planned"){
    Posda::EditStateChange::Trans(
      $inv, "Edits Planned", "Comparisons In Progress");
    $disposition = "Comparisons In Progress";
  }

  # num_ready of 0 means there is nothing claimable but the run has not been
  # advanced yet -- the state a killed worker leaves behind between finishing
  # the last file and running the transition. Skip straight to the completion
  # check rather than issuing three claims that cannot match anything.
  if($num_ready > 0){
    # Compares first: they gate completion of the whole run, and draining them
    # keeps finished edits from piling up unreported.
    $did += process_batch($inv, "pending_compare", "comparing", \&do_compare);
    return $did if $ShuttingDown;
    $did += process_batch($inv, "pending_import",  "importing", \&do_import);
    return $did if $ShuttingDown;
    $did += process_batch($inv, "pending_edit",    "editing",   \&do_edit);
    return $did if $ShuttingDown;
  }

  update_progress_and_finish($inv, $disposition);
  return $did;
}

#############################
# Main loop.
my $idle = $IDLE_MIN;
while(!$ShuttingDown){
  my $active = eval { $q_active->FetchResults() };
  if($@){
    print STDERR "error looking for work: $@\n";
    sleep $IDLE_MAX;
    next;
  }

  my $did = 0;
  if(defined($active) && ref($active) eq "ARRAY"){
    for my $row (@$active){
      last if $ShuttingDown;
      my($inv, $disposition, $num_ready) = @{$row}[0, 1, 2];
      $did += eval { work_on_edit($inv, $disposition, $num_ready) } || 0;
      if($@){ print STDERR "edit $inv: $@\n" }
    }
  }

  if($did){
    $idle = $IDLE_MIN;
  } else {
    last if $ShuttingDown;
    sleep $idle;
    $idle *= 2;
    $idle = $IDLE_MAX if $idle > $IDLE_MAX;
  }
}

print "EditWorkerLoop $WorkerId shutting down cleanly\n";
exit 0;
