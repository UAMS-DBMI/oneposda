#
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
use strict;
package Posda::EditFile;

# The DICOM edit engine, lifted out of NewSubprocessEditor.pl so it can be
# called in-process by a worker instead of only as a fork+exec'd child that
# speaks Storable over a socketpair.
#
# The edit operations below are a verbatim port. They are the correctness gate
# for the whole distributed pipeline: because the engine is deterministic (no
# timestamps in WritePart10, all hashing MD5-derived), the same input file and
# spec must produce a byte-identical output file, which is what makes a retried
# edit safe after a worker is killed. Any behavioural change here breaks that
# guarantee, so resist tidying these ops -- including the odd-looking ones.
#
# Two things differ from the original, both outside the edit logic:
#
#  1) The output is written to a temp file, fsync'd, and rename()d into place.
#     The original opened the destination with '>' and streamed into it, so a
#     worker killed mid-write left a truncated .dcm behind.
#  2) Failures return a result hash instead of calling exit(), and exceptions
#     escaping Posda::Dataset are caught, so one malformed file cannot take down
#     a worker that is processing a batch.

use Posda::Try;
use Posda::UUID;
use Posda::PrivateDispositions;
use Digest::MD5;
use File::Basename qw( dirname );
use File::Path qw( make_path );
use IO::Handle;

require Exporter;
our @ISA = ( 'Exporter' );
our @EXPORT_OK = ( 'apply_edits' );

# Per-file chatter is fine for one file, ruinous for millions. The original
# printed an unconditional Debug::GenPrint dump of every edit spec plus a
# running commentary; keep it available, off by default.
our $DEBUG = $ENV{POSDA_EDIT_DEBUG} ? 1 : 0;
sub _dbg;
sub _dbg { return unless $DEBUG; print STDERR @_ }

# Unwinds to apply_edits' eval with a populated result hash.
sub _fail {
  my($message, $addl) = @_;
  my $e = { Status => "Error", message => $message };
  if($addl){ $e->{additional_info} = $addl }
  die $e;
}

sub SearchLeaf{
  my($leaf_tag, $tag_list) = @_;
  my $sub = sub {
    my($ele, $sig) = @_;
    my $pat = $leaf_tag;
    $pat =~ s/\(/\\(/g;
    $pat =~ s/\)/\\)/g;
    if($sig =~ /$pat$/){
      push(@$tag_list, $sig);
    } else {
    }
  };
  return $sub;
}

sub digest_of {
  my($path) = @_;
  open(my $fh, '<', $path) or return undef;
  binmode $fh;
  my $ctx = Digest::MD5->new;
  $ctx->addfile($fh);
  close $fh;
  return $ctx->hexdigest;
}

# apply_edits($from_file, $to_file, $spec) -> result hashref
#
# $spec is the same structure NewSubprocessEditor.pl has always accepted:
#   { edits => [ {op, tag, tag_mode, arg1, arg2}, ... ],
#     uid_substitutions   => { <from_uid> => <to_uid>, ... },   # optional
#     uid_root_transform  => { from => <root>, to => <root> } } # optional
#
# Returns { Status => "OK", from_file, to_file, from_digest, to_digest } or
# { Status => "Error", message, additional_info }. The OK/Error keys and the
# from_file/to_file keys are what the Storable wire format already carried, so
# NewSubprocessEditor.pl can hand this straight back to its existing callers.
sub apply_edits {
  my $result = eval { _apply_edits(@_) };
  if($@){
    return $@ if ref($@) eq 'HASH';
    return { Status => "Error", message => "$@" };
  }
  return $result;
}

sub _apply_edits {
  my($from_file, $to_file, $spec) = @_;
  my $results = {};
  my $edits = { %{ $spec || {} }, from_file => $from_file, to_file => $to_file };

  unless(exists $edits->{from_file}){ _fail("No from_file in edits") }
  unless(-f $edits->{from_file}){ _fail("file not found: $edits->{from_file}") }
  $results->{from_file} = $edits->{from_file};
  my $map_uids = sub {
    my($ele, $sig) = @_;
  #  if($ele->{vr} eq "UI"){
      if($ele->{type} eq "text"){
        if($ele->{value} && ref($ele->{value}) eq "ARRAY"){
          for my $i (0 .. $#{$ele->{value}}){
            my $from = $ele->{value}->[$i];
            if(exists($edits->{uid_subsitutions}->{$from})){
              my $to = $edits->{uid_substitutions}->{$from};
              $ele->{value}->[$i] = $to;
            }
          }
        } elsif($ele->{value}){
           my $from = $ele->{value};
          if(exists $edits->{uid_substitutions}->{$from}){
            my $to = $edits->{uid_substitutions}->{$ele->{value}};
            $ele->{value} = $to;
          }
        } else {
        }
      }
  #  }
  };
  my $transform_uids = sub {
    my($ele, $sig) = @_;
  #  if($ele->{vr} eq "UI"){
      if($ele->{type} eq "text"){
        if($ele->{value} && ref($ele->{value}) eq "ARRAY"){
          for my $i (0 .. $#{$ele->{value}}){
            my $from = $ele->{value}->[$i];
            if($from =~ /^$edits->{uid_root_transform}->{from}(.*)$/){
              my $remain = $1;
              my $to = "$edits->{uid_root_transform}->{to}$remain";
              $ele->{value}->[$i] = $to;;
            }
          }
        } elsif($ele->{value}){
          my $from = $ele->{value};
          if($from =~ /^$edits->{uid_root_transform}->{from}(.*)$/){
            my $remain = $1;
            my $to = "$edits->{uid_root_transform}->{to}$remain";
            $ele->{value} = $to;
          }
        } else {
        }
      }
  #  }
  };
  my $try = Posda::Try->new($edits->{from_file});
  unless(exists $try->{dataset}) {
    _fail("file $edits->{from_file} didn't parse", $try);
  }
  my $ds = $try->{dataset};
  if(exists $edits->{uid_substitutions}){
    my $num_subs = keys %{$edits->{uid_substitutions}};
    if($num_subs >= 0){
      $ds->MapPvt($map_uids);
    }
  } 
  if(exists $edits->{uid_root_transform}){
  _dbg "Found uid_root_transform\n";
    $ds->MapPvt($transform_uids);
  } 
  
  my @effective_edits;
  for my $edit(@{$edits->{edits}}){
    my $op = $edit->{op};
    my $tag = $edit->{tag};
    my $tag_mode = $edit->{tag_mode};
    my $arg1 = $edit->{arg1};
    my $arg2 = $edit->{arg2};
    if($tag_mode eq "exact" || $tag_mode eq "item"){
      push(@effective_edits, [$tag, $op, $arg1, $arg2]);
  #    if($tag_mode eq "item"){
  #      _dbg "Item edit: [$tag, $op, $arg1, $arg2]\n";
  #    }
    }elsif($tag_mode eq "pattern"){
      my $list = $ds->Search($tag);
      if(defined($list) && ref($list) eq "ARRAY" && $#{$list} >= 0){
        for my $m (@$list){
          my $tag_inst = $ds->DefaultSubstitute($tag, $m);
          push(@effective_edits, [$tag_inst, $op, $arg1, $arg2]);
  _dbg "pushing [$tag_inst, $op, $arg1, $arg2] to effective edits\n";
        }
      }
    }elsif($tag_mode eq "leaf"){
      my @tags;
      $ds->MapPvt(SearchLeaf($tag, \@tags));
      for my $tag_inst (@tags){
        push(@effective_edits, [$tag_inst, $op, $arg1, $arg2]);
      }
    }elsif($tag_mode eq "group_pattern"){
      unless($op eq "delete_matching_group"){
        die "tag_mode of group_pattern with op $op";
      }
      unless($tag eq "60xx" || $tag eq "50xx"){
        _dbg "delete matching group: $tag\n";
      }
      push(@effective_edits, [$tag, $op, $arg1, $arg2]);
    }elsif($tag_mode eq "private_group"){
      unless($tag =~ /^[\da-f][\da-f][\da-f][13579bdf]$/){
        die "tag_mode of private_group with group $tag";
      }
      unless($op eq "move_owner_block"){
        die "tag_mode of private_group with op $op";
      }
      push(@effective_edits, [$tag, $op, $arg1, $arg2]);
    }
  }
  for my $e (@effective_edits){
    my($etag, $eop, $earg1, $earg2) = @$e;
    if($eop eq "shift_date"){
      my $value = $ds->Get($etag);
      if(ref($value) eq "ARRAY"){
        for my $i (0 .. $#{$value}){
          my $val = $value->[$i];
          if(defined $val ){
            my $shifter = Posda::PrivateDispositions->new(
              undef, $earg1, undef, undef);
            my $new_value;
            eval {
              $new_value = $shifter->ShiftDate($value);
            };
            if($@){
              _dbg "Error ($@) shifting date: $val\n" .
                "not changed\n";;
            } else {
              $value->[$i] = $val
            }
          }
        }
      } else {
        if(defined $value ){
          my $shifter = Posda::PrivateDispositions->new(
            undef, $earg1, undef, undef);
          my $new_value;
          eval {
            $new_value = $shifter->ShiftDate($value);
          };
          if($@){
            _dbg "Error ($@) shifting date: $value\n" .
              "not changed\n";;
          } else {
            $ds->Insert($etag, $new_value);
          }
        }
      }
    }elsif($eop eq "shift_date_by_year"){
      my $value = $ds->Get($etag);
      if(defined $value){
        if($value =~ /^(\d\d\d\d)(.*)/){
          my $year = $1;
          my $rem = $2;
          $year += $earg1;
          my $new_date = sprintf("%4d",$year) . $rem;
          $ds->Insert($etag, $new_date);
        }
      }
    }elsif($eop eq "copy_date_from_tag_to_dt"){
      my $value = $ds->Get($etag);
      my $sub_date = $ds->Get($earg1);
      if($value =~/^........(.*)$/){
        my $remain = $1;
        if(length($sub_date) == 8){
          my $new_value = "$sub_date$remain";
          $ds->Insert($etag, $new_value);
        }
      }
    }elsif($eop eq "copy_from_tag"){
      my $value = $ds->Get($earg1);
      $ds->Insert($etag, $value);
    }elsif($eop eq "delete_tag"){
      $ds->Delete($etag);
    }elsif($eop eq "set_tag"){
      $ds->Insert($etag, $earg1);
    }elsif($eop eq "substitute"){
      my $value = $ds->Get($etag);
      if($value eq $earg1){
        $ds->Insert($etag, $earg2);
      }
    }elsif($eop eq "string_replace"){
      my $value = $ds->Get($etag);
      my $value1 = $value;
      $value1 =~ s/$earg1/$earg2/g;
      if($value ne $value1){
        $ds->Insert($etag, $value1);
      }
    }elsif($eop eq "empty_tag"){
      $ds->Insert($etag, "");
    }elsif($eop eq "short_hash"){
      my $value = $ds->Get($etag);
      my $ctx = Digest::MD5->new;
      $ctx->add($value);
      my $dig = $ctx->hexdigest;
      my $len = length($value);
      my $new_str = substr($dig, 0, $len);
      $ds->Insert($etag, $new_str);
    }elsif($eop eq "hash_unhashed_uid"){
      my $value = $ds->Get($etag);
      unless($value =~ /^$earg1.*$/){
        # Remove any leading ! from the new root. This allows
        # a user to force hashing of a UID with the same root 
        # by suppying the new root with a leading !, example:
        # !1.2.3.4567
        $earg1 =~ s/^\!//;
        my $ctx = Digest::MD5->new;
        $ctx->add($value);
        my $dig = $ctx->digest;
        my $new_uid = "$earg1." . Posda::UUID::FromDigest($dig);
        $ds->Insert($etag, $new_uid);
      }
    }elsif($eop eq "date_difference"){
      my $val;
      my $date_in_tag = $ds->Get($earg1);
      my $date = $earg2;
      eval {
        $val = Posda::PrivateDispositions->DiffDate(
          $date, $date_in_tag);
      };
      if($@){
        $val = "error in computation: $@";
      }
      $ds->Insert($etag, $val);
    }elsif($eop eq "delete_matching_group"){
      for my $gr (keys %{$ds}){
        my $group = sprintf("%4x", $gr);
        if($etag eq '60xx' && $group =~ /^60..$/){
          delete $ds->{$gr};
        }
        if($etag eq '50xx' && $group =~ /^50..$/){
          delete $ds->{$gr};
        }
      }
    }elsif($eop eq "move_owner_block"){
      my $gr = hex($etag);
      my $owner = $earg1;
      my $bl = hex($earg2);
      $ds->MapToConvertPvt;
      if(exists $ds->{$gr}){
        my $private_map = $ds->{$gr}->{private_map};
        my $r_private_map = $ds->{$gr}->{r_private_map};
        unless($r_private_map->{$owner} == $bl){
          my $cur_blk = $r_private_map->{$owner};
          if(exists $private_map->{$bl}){
            my $to_move_own = $private_map->{$bl};
  	  $private_map->{$cur_blk} = $to_move_own;
            $r_private_map->{$to_move_own} = $cur_blk;
          }
          $private_map->{$bl} = $owner;
          $r_private_map->{$owner} = $bl;
          # So differences show up
          $ds->Insert('(0013,"Posda",01)', "private tag blocks reallocated");
        }
      }
      $ds->MapToConvertPvtBack;
    }elsif($eop eq "annotate_img"){
      my $pix_desc = $ds->GetEle("(7fe0,0010)");
      unless(
        defined($pix_desc) &&
        ref($pix_desc) eq "HASH" &&
        defined ($pix_desc->{file_pos}) &&
        defined ($pix_desc->{ele_len_in_file})
      ){
        _dbg "No pixel data to annotate\n";
      } else {
        my $rows = $ds->Get("(0028,0010)");
        my $cols = $ds->Get("(0028,0011)");
        my $bits_allocated = $ds->Get("(0028,0100)");
        my $bits_stored = $ds->Get("(0028,0101)");
        my $high_bit = $ds->Get("(0028,0102)");
        my $photometric_interpretation = $ds->Get("(0028,0004)");
        my $pixel_representation = $ds->Get("(0028,0103)");
        my $cmd = "annotate_img.py \"$edits->{from_file}\" \"$pix_desc->{file_pos}\" " .
  #        "\"$pix_desc->{ele_len_in_file}\" " .
          "\"$rows\" \"$cols\" \"$bits_allocated\" \"$bits_stored\" \"$high_bit\" " .
          "\"$photometric_interpretation\" \"$pixel_representation\" '$earg1'";
  _dbg "###################\nCommand:\n$cmd\n###############\n";
        my $pix = do {
          local $/;
          open my $fh, "$cmd|" or die "Can't open pipe from ($cmd): $!";
          <$fh>
        };
        $ds->Insert("(7fe0,0010)", $pix);
      }
    }elsif($eop eq "add_tag_to_seq"){
      my $seq = $ds->Get($etag);
      if(defined $seq){
        my $seq_ref = ref($seq);
        _dbg "Got a seq of ref($seq_ref)\n";
        my $count = @$seq;
        _dbg "has $count elements\n";
        for my $n (0 .. $#{$seq}){
          my $iref = ref($seq->[$n]);
          my $item = $seq->[$n];
          $item->Insert($earg1, $earg2);
          _dbg "item->Insert($earg1, $earg2)\n";
        }
      }
    }else{
      _fail("unknown eop ($eop)");
  _dbg "unknown eop: $eop\n";
    }
  }
  my $xfr_stx = $try->{xfr_stx};
  if($xfr_stx eq "1.2.840.10008.1.2.2"){
    _dbg "converting file from big to little endian transfer syntax\n";
    $xfr_stx = "1.2.840.10008.1.2.1";
  }

  # Atomic publish. WritePart10 opens with '>' and streams, so writing straight
  # to $to_file leaves a truncated file if the process dies mid-write. Write
  # beside the target, fsync, then rename -- rename(2) within a directory is
  # atomic, so a reader either sees no file or sees the whole file.
  my $dir = dirname($edits->{to_file});
  unless(-d $dir){
    eval { make_path($dir) };
    if($@ or not -d $dir){
      _fail("Can't create directory $dir", $@);
    }
  }
  my $tmp = "$edits->{to_file}.tmp.$$";
  eval {
    $ds->WritePart10($tmp, $xfr_stx, "POSDA", undef, undef);
  };
  if($@){
    unlink $tmp;
    _dbg "Can't write $tmp ($@)\n";
    _fail("Can't write $edits->{to_file}", $@);
  }
  # Durability before the rename: without it a node crash can leave a file that
  # exists at its final name but has never reached disk, whose digest we already
  # recorded as good.
  if(open(my $sfh, '+<', $tmp)){
    eval { $sfh->sync };
    close $sfh;
  }
  my $to_digest = digest_of($tmp);
  unless(rename($tmp, $edits->{to_file})){
    my $err = $!;
    unlink $tmp;
    _fail("Can't rename $tmp to $edits->{to_file} ($err)");
  }

  $results->{to_file}     = $edits->{to_file};
  $results->{from_digest} = $try->{digest};
  $results->{to_digest}   = $to_digest;
  $results->{Status}      = "OK";
  return $results;
}

1;
