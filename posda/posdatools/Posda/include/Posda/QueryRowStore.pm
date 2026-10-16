#!/usr/bin/perl -w
#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
package Posda::QueryRowStore;
#
# Disk-backed storage for the rows of a foreground query result.
#
# The query UIs used to keep every row of a result in a Perl array for as
# long as the result stayed open. A Perl array-of-arrays costs well over a
# hundred bytes per cell, so large results pushed the app server past its
# container memory limit even though only one page of rows is ever shown.
#
# This stores rows in a temp file instead, one JSON-encoded row per line, and
# reads back only the rows a caller asks for. The only per-row state kept in
# memory is a sparse index: the byte offset of every INDEX_STRIDE-th row.
# Fetching row N seeks to the start of its block and skips at most
# INDEX_STRIDE - 1 lines, which is cheap for the page-sized reads the UI does.
#
# Rows may be appended while earlier rows are being read (a query streams
# rows in while the user pages through partial results). Reads never go past
# `count`, and the write buffer is flushed before every read, so a reader
# never sees a half-written line.
#
# The file is removed when the last reference to the store goes away.
#
use strict;
use warnings;
use IO::Handle;
use JSON;

my $INDEX_STRIDE = 256;
my $Sequence = 0;

# new($dir, $label) - create an empty store backed by a new file in $dir.
# $label only makes the file name recognisable; uniqueness comes from the
# pid and a per-process sequence number.
sub new {
  my ($class, $dir, $label) = @_;
  unless (defined $dir && -d $dir) {
    die "Posda::QueryRowStore: directory " .
      (defined $dir ? "'$dir'" : "(undef)") . " does not exist";
  }
  $label = "rows" unless defined $label;
  $label =~ s/[^\w.-]/_/g;
  $Sequence += 1;
  my $path = "$dir/$label.$$.$Sequence.jsonl";
  open my $wfh, ">", $path or die "Can't open $path for writing: $!";
  binmode $wfh;
  my $self = {
    path => $path,
    wfh => $wfh,
    rfh => undef,
    count => 0,
    bytes_written => 0,
    block_offsets => [],
    # ascii mode: every non-ASCII character is \u-escaped, so the file is
    # valid however the source strings were flagged, and values round-trip
    # character for character.
    json => JSON->new->ascii,
  };
  return bless $self, $class;
}

sub path { return $_[0]->{path} }

sub count { return $_[0]->{count} }

# add(\@row) - append one row.
sub add {
  my ($self, $row) = @_;
  if ($self->{count} % $INDEX_STRIDE == 0) {
    push @{$self->{block_offsets}}, $self->{bytes_written};
  }
  my $line = $self->{json}->encode($row) . "\n";
  print {$self->{wfh}} $line or die "Can't write to $self->{path}: $!";
  $self->{bytes_written} += length($line);
  $self->{count} += 1;
}

# row($i) - the i-th row (0-based), or undef if out of range.
sub row {
  my ($self, $index) = @_;
  my $rows = $self->rows($index, 1);
  return $rows->[0];
}

# rows($first, $n) - up to $n consecutive rows starting at $first, clamped
# to what the store holds. Always returns an array ref.
sub rows {
  my ($self, $first, $n) = @_;
  my @rows;
  $first = 0 unless defined $first;
  $n = 0 unless defined $n;
  if ($first < 0) { $first = 0 }
  if ($n <= 0 || $first >= $self->{count}) { return \@rows }
  my $last = $first + $n - 1;
  if ($last > $self->{count} - 1) { $last = $self->{count} - 1 }
  my $fh = $self->_reader_positioned_at($first);
  local $/ = "\n";
  for my $i ($first .. $last) {
    my $line = <$fh>;
    unless (defined $line) {
      die "Posda::QueryRowStore: $self->{path} ended before row $i " .
        "(expected $self->{count} rows)";
    }
    push @rows, $self->{json}->decode($line);
  }
  return \@rows;
}

# each(sub { my ($row, $i) = @_; ... }) - stream every row through a callback
# without holding them all in memory. The callback must not read from this
# same store (it shares the read handle); writing to a different store, as a
# filter does, is fine.
sub each {
  my ($self, $callback) = @_;
  if ($self->{count} == 0) { return }
  my $fh = $self->_reader_positioned_at(0);
  local $/ = "\n";
  for my $i (0 .. $self->{count} - 1) {
    my $line = <$fh>;
    unless (defined $line) {
      die "Posda::QueryRowStore: $self->{path} ended before row $i " .
        "(expected $self->{count} rows)";
    }
    &$callback($self->{json}->decode($line), $i);
  }
}

# all_rows() - every row as one array ref. This rebuilds the in-memory
# structure the store exists to avoid, so it is only for callers that hand
# the whole result set to something else and have no streaming alternative.
sub all_rows {
  my ($self) = @_;
  my @rows;
  $self->each(sub { push @rows, $_[0] });
  return \@rows;
}

# cursor() - a forward-only reader over the rows present when each next()
# call is made. It has its own file handle, so page reads on the store can
# go on while a long-running consumer (a CSV download) works through it.
sub cursor {
  my ($self) = @_;
  return Posda::QueryRowStore::Cursor->new($self);
}

sub _reader_positioned_at {
  my ($self, $index) = @_;
  # Pending writes have to hit the file before a reader can see them.
  $self->{wfh}->flush;
  my $fh = $self->{rfh};
  unless (defined $fh) {
    open $fh, "<", $self->{path} or die "Can't open $self->{path}: $!";
    binmode $fh;
    $self->{rfh} = $fh;
  }
  my $block = int($index / $INDEX_STRIDE);
  my $offset = $self->{block_offsets}->[$block];
  unless (defined $offset) {
    die "Posda::QueryRowStore: no index block for row $index";
  }
  seek($fh, $offset, 0) or die "Can't seek in $self->{path}: $!";
  local $/ = "\n";
  for (1 .. $index % $INDEX_STRIDE) {
    my $skipped = <$fh>;
  }
  return $fh;
}

sub DESTROY {
  my ($self) = @_;
  if (defined $self->{wfh}) { close $self->{wfh} }
  if (defined $self->{rfh}) { close $self->{rfh} }
  if (defined $self->{path} && -e $self->{path}) {
    unless (unlink $self->{path}) {
      print STDERR "Posda::QueryRowStore: can't remove $self->{path}: $!\n";
    }
  }
}

package Posda::QueryRowStore::Cursor;

use strict;
use warnings;

sub new {
  my ($class, $store) = @_;
  $store->{wfh}->flush;
  open my $fh, "<", $store->{path} or die "Can't open $store->{path}: $!";
  binmode $fh;
  return bless { store => $store, fh => $fh, next_index => 0 }, $class;
}

# next($n) - up to $n rows following the last call, or undef once every row
# the store held at the time of the call has been returned.
sub next {
  my ($self, $n) = @_;
  my $store = $self->{store};
  my $available = $store->count - $self->{next_index};
  if ($available <= 0) { return undef }
  if ($n > $available) { $n = $available }
  $store->{wfh}->flush;
  my $fh = $self->{fh};
  my @rows;
  local $/ = "\n";
  for (1 .. $n) {
    my $line = <$fh>;
    unless (defined $line) {
      die "Posda::QueryRowStore: $store->{path} ended before row " .
        "$self->{next_index} (expected " . $store->count . " rows)";
    }
    push @rows, $store->{json}->decode($line);
    $self->{next_index} += 1;
  }
  return \@rows;
}

sub DESTROY {
  my ($self) = @_;
  if (defined $self->{fh}) { close $self->{fh} }
}

1;
