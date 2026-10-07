#!/usr/bin/perl -w
use strict;
use Posda::BackgroundProcess;
use Posda::DB 'Query';
use Posda::QueryLog;
my $usage = <<EOF;
RunQueryInBackground.pl <?invoc_id?> <activity_id> <query_name> <notify>
or
RunQueryInBackground.pl -h

Expects input lines in following format:
<arg>

The number of args must match the number of args in the specified query
EOF
if($#ARGV == 0 && $ARGV[0] eq "-h"){
  print "$usage\n";
  exit;
}
unless($#ARGV == 3) {
  print "Wrong number of args: $#ARGV vs 2\n";
  exit;
}

# Excel (and LibreOffice Calc) stop at 1,048,576 rows per sheet. Each output
# file is capped at 75% of that, counting the header row, so every file opens
# cleanly in a spreadsheet with room to spare.
my $ExcelMaxRows = 1_048_576;
my $MaxLinesPerFile = int($ExcelMaxRows * 0.75);
my $MaxDataRowsPerFile = $MaxLinesPerFile - 1;

my($invoc_id, $activity_id, $query_name, $notify) = @ARGV;
my @Args;
while(my $line = <STDIN>){
  chomp $line;
  push @Args, $line;
}
my $num_args = @Args;
print "Going to background after reading $num_args args\n";
my $back = Posda::BackgroundProcess->new($invoc_id, $notify, $activity_id);
$back->Daemonize;
my $Query = PosdaDB::Queries->GetQueryInstance($query_name);
my $qh = Query($query_name);
my $QueryInvokedId = Posda::QueryLog::query_invoked($Query, $notify);

# Rows are streamed straight from the statement handle into the report
# files rather than buffered in Perl. RunQueryWithRowCount tells us the
# total before the first row arrives, so file names and the email summary
# can still be sized up front.
my $start = time;
my $elapsed;
my $num_rows;
my $num_files;
my $rows_written = 0;
my $pipe;
eval {
  $qh->RunQueryWithRowCount(
    sub {
      ($num_rows) = @_;
      # The DB work is done once execute returns; the rest is writing files
      $elapsed = time - $start;
      $num_files = NumberOfOutputFiles($num_rows);
    },
    sub {
      my($row) = @_;
      if($rows_written % $MaxDataRowsPerFile == 0){
        my $file_num = int($rows_written / $MaxDataRowsPerFile) + 1;
        $pipe = StartReportFile($back, $Query, $file_num, $num_files);
      }
      $pipe->print(CsvLine($row));
      $rows_written++;
    },
    @Args);
};
if($@){
  my $err = $@;
  $back->WriteToEmail("Query $query_name failed:\n$err\n");
  $back->Finish("Query failed");
  exit;
}
if($num_rows == 0){
  # Still produce a (header-only) file so the user gets something to open
  StartReportFile($back, $Query, 1, 1);
}
Posda::QueryLog::query_finished($QueryInvokedId, $rows_written);

WriteSummaryToEmail($back, $Query, $invoc_id, $query_name, $notify,
  $elapsed, \@Args, $rows_written, $num_files);
$back->Finish;

sub WriteSummaryToEmail {
  my($back, $Query, $invoc_id, $query_name, $notify, $elapsed, $args,
    $num_rows, $num_files) = @_;
  my $when = `date`;
  chomp $when;
  $back->WriteToEmail("Background Query\n");
  $back->WriteToEmail("subprocess_invocation_id: $invoc_id\n");
  $back->WriteToEmail("query_name: $query_name\n");
  $back->WriteToEmail("run_by: $notify\n");
  $back->WriteToEmail("seconds: $elapsed\n");
  $back->WriteToEmail("when: $when\n");
  $back->WriteToEmail("\nargs:\n");
  for my $i (0 .. $#{$Query->{args}}){
    $back->WriteToEmail("\t$Query->{args}->[$i]: $args->[$i]\n");
  }
  $back->WriteToEmail(
    "\nQuery $query_name returned $num_rows rows in $elapsed seconds\n");
  $back->WriteToEmail(
    "Rows are split across $num_files file(s) of at most " .
    "$MaxDataRowsPerFile rows each\n\n");
}

sub NumberOfOutputFiles {
  my($num_rows) = @_;
  if($num_rows == 0){ return 1 }
  return int(($num_rows + $MaxDataRowsPerFile - 1) / $MaxDataRowsPerFile);
}

# Open the next report file and write the column header row into it
sub StartReportFile {
  my($back, $Query, $file_num, $num_files) = @_;
  my $pipe = $back->CreateReport(ReportName($file_num, $num_files));
  $pipe->print(CsvLine($Query->{columns}));
  return $pipe;
}

sub ReportName {
  my($file_num, $num_files) = @_;
  if($num_files == 1){ return "Query Results" }
  # Zero-padded so the reports sort in order in the email and the UI
  my $width = length($num_files);
  return sprintf("Query Results %0${width}d of %d", $file_num, $num_files);
}

sub CsvLine {
  my($values) = @_;
  my @quoted;
  for my $val (@$values){
    unless(defined $val){ $val = "" }
    $val =~ s/"/""/g;
    push @quoted, "\"$val\"";
  }
  return join(",", @quoted) . "\n";
}
