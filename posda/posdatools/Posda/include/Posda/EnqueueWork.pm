#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
package Posda::EnqueueWork;

# Enqueue a spreadsheet_operation as a background job, the same way the UI does.
#
# The create-invocation / create-work-row / lpush sequence was copy-pasted into
# NewerProcessPopup.pm, BackgroundQuery.pm and BulkRenderRoiSlices.pm before
# this existed. The distributed editor needs it too -- a worker has to hand the
# finished run off to the report job -- so it lives in one place now rather than
# being pasted a fourth time.

use Modern::Perl '2010';
use Posda::DB 'Query';
use Posda::Config 'Config';
use Posda::File::Import;
use File::Temp qw( tempfile );
use Redis;

require Exporter;
our @ISA = ( 'Exporter' );
our @EXPORT_OK = ( 'enqueue_operation' );

use constant REDIS_HOST => Config('redis_host') . ':6379';

# enqueue_operation($operation_name, \@input_lines, $invoking_user, \%subs)
#   -> ($work_id, $subprocess_invocation_id)
#
# @input_lines is what the operation would have received on STDIN; pass an empty
# arrayref for operations that take none.
#
# %subs fills in the command_line's angle-bracket placeholders, e.g.
# { activity_id => 12, notify => 'someone' } turns "<activity_id>" into "12".
# This has to happen here because WorkerNode.py only ever substitutes
# <?bkgrnd_id?>; every other placeholder is expected to have been resolved
# before the row was written to subprocess_invocation, which is what the UI
# popup does with its own parameters.
sub enqueue_operation {
  my($operation_name, $input_lines, $invoking_user, $subs) = @_;
  $input_lines ||= [];
  $subs ||= {};
  $invoking_user = 'posda' unless defined $invoking_user;

  my $op = Query("GetSpreadsheetOperationByName")
             ->FetchOneHash($operation_name);
  unless($op && $op->{command_line}){
    die "No spreadsheet_operation named $operation_name";
  }

  my $command_line = $op->{command_line};
  for my $k (keys %$subs){
    my $v = $subs->{$k};
    # Substituting an empty string removes a word from the command line rather
    # than passing an empty argument, so a job that checks its argument count
    # would fail confusingly. Refuse it here instead.
    unless(defined($v) && length($v)){
      die "Refusing to substitute an empty value for <$k> in $operation_name";
    }
    $command_line =~ s/<\Q$k\E>/$v/g;
  }
  if($command_line =~ /<(?!\?bkgrnd_id\?)([a-z_]+)>/){
    die "Unexpanded placeholder <$1> in command line for $operation_name";
  }

  my $invoc = Query("CreateSubprocessInvocationButton")
                ->FetchOneHash(undef, $operation_name, $command_line,
                               undef, $invoking_user, $operation_name);
  my $new_id = $invoc ? $invoc->{subprocess_invocation_id} : undef;
  unless($new_id){
    die "Couldn't create row in subprocess_invocation for $operation_name";
  }

  # Worker nodes feed the job's stdin from a file held in Posda, so even an
  # operation with no input needs a file to point at.
  my($fh, $tmp) = tempfile();
  for my $l (@$input_lines){ print $fh "$l\n" }
  close $fh;
  my $resp = Posda::File::Import::insert_file($tmp);
  unlink $tmp;
  if($resp->is_error){
    die "Couldn't import input file for $operation_name: " . $resp->message;
  }
  my $input_file_id = $resp->file_id;

  my $prio = Query("OperationPriority")->FetchOneHash($operation_name);
  my $priority = ($prio && defined $prio->{worker_priority})
    ? $prio->{worker_priority} : 0;
  my $queue = "work_queue_$priority";

  my $work = Query("CreateNewWorkWithPriority")
               ->FetchOneHash($new_id, $input_file_id, $queue);
  my $work_id = $work ? $work->{work_id} : undef;
  unless($work_id){
    die "Couldn't create work row for $operation_name";
  }

  my $redis = Redis->new(server => REDIS_HOST);
  unless($redis){ die "Couldn't connect to redis" }
  $redis->lpush($queue, $work_id);
  $redis->quit;

  return ($work_id, $new_id);
}

1;
