#!/usr/bin/perl -w
#
#Copyright 2013, Bill Bennett
# Part of the Posda package
# Posda may be copied only under the terms of either the Artistic License or the
# GNU General Public License, which may be found in the Posda Distribution,
# or at http://posda.com/License.html
#
# The edit engine itself now lives in Posda::EditFile so it can also be called
# in-process by EditWorkerLoop.pl, which avoids paying a fork, an exec and a
# full interpreter startup for every DICOM file. This script remains the
# Storable-over-a-socketpair front end that BackgroundEditorTp.pl,
# BackgroundEditBySopInstanceTp.pl, BackgroundDoProposedEdits.pl and
# BackgroundOnlyEditDicomSeries.pl already speak; the wire format is unchanged.
#
use strict;
use Posda::EditFile;
use Storable qw( store_fd fd_retrieve );
my $help = <<EOF;
 Anonymizer meant to run as a sub-process
 Receives parameters via fd_retrive from STDIN.
 Writes results to STDOUT via store_fd
 incoming data structure:
 \$in = {
   from_file => <path to from file>,
   to_file => <path to to file>,
   uid_substitutions => {
     <from_uid> => <to_uid>,
     ...
   },
   uid_root_transform => {
     from => <from_uid_root>,
     to  => <to_uid_root>
   },
   edits => [
     <edit_spec>,
     ...
   ],
 };

  where:
  <uid_substitutions> is optional.
  <uid_root_transform> is optional.

  <edit_spec> = {
    op => <operation>,
    tag => <tag>,
    tag_mode => "exact|pattern|leaf|item|group_pattern|private_group",
    arg1 => <arg1 of op>,
    arg2 => <arg2 of op>
  };

  <tag> is either an exact tag e.g:
    (0010,0010)
    (0013,"CTP",50)
    (0054,0016)[0](0018,1078)
  or a tag pattern (which specifes a number of matching tags), e.g:
    (0054,0016)[<0>](0018,1078)
  or a "leaf" tag (which specifies any "leaf" occurance of a tag), e.g:
    (0018,1078) 
  or an item in a multi-valued tag, e.g:
    (0008,0008)[7]
  or a group_pattern, e.g:
    60xx
    50xx
  or a private_group, e.g:
    0013

  <tag_mode> specifies the type of tag. If the tag specified is a pattern,
  and <tag_mode> is not "pattern", then this program will crash because of
  an uncaught exception in Posda::Dataset.  Generally the parent program 
  should insure this doesn't happen.
  Also, specifying a item in a multi-valued tag for a tag which is not a
  multi-valued tag can cause problems.  The parent program can only give
  you so much help here.  Caveat usor.

  <op> specifies the operation to be performed on the tag or tags identified
  by <tag> and <tag_mode>
  <arg1> and <arg2> are the arguments of these operands:
    shift_date(number_of_days) - shift a date by an integer number of days.
                                 to shift backwards supply negative integer.
    shift_date_by_year(number_of_years) - shift a date by an integer number of years.
                                 to shift backwards supply negative integer.
    delete_tag() - Delete the tag
    set_tag(value) - Set the value of a tag unconditionally.
                     Even if not present.
    substitute(existing_value, new_value) - Set the value of the tag only if
                                            its current value matches
                                            existing_value
    string_replace(old_text, new_text) - replace any occurance of <old_text>
                                         with <new_text> in the string value
                                         of the tag.
    empty_tag() - Empty the tag (set it to empty value).
                  Even if tag is not present.
    hash_unhashed_uid(uid_root) - hash the value of the tag unless the current
                                  value of the tag is either empty, or matches
                                  the supplied uid_root
    date_difference(ref_tag, date) - Replace value in tag with number of days
                                     from date to date in ref_tag. 
                                     negative if date in ref_tag preceeds date
                                     positive if date preceeds date in ref_tag
                                     i.e. date is "from", ref_tag_date is "to"
                                     difference is "to - from"
                                     Typically, date is "date of diagnosis" and
                                     tag is (0008,0020) (Study Date).
                                     If there is an error computing difference,
                                     value of tag is replaced with error message,
                                     which may be verbose
   copy_from_tag(from_tag) - Copy the value in from_tag to tag
   delete_matching_group() - tag_mode must be 'group_pattern', tag specifies pattern
                             deletes all of the groups matching the pattern
   move_owner_block(owner, block) - tag_mode must be private_group, tag specifies 
                                    block owner (e.g. "CTP").  Moves owners tags to
                                    specified allocated block (moving other tags
                                    as necessary). This operation is to simulate
                                    CTP's behaviour (blindly putting data in block 10,
                                    regardless of what is already there).

   Order of processing:
   1) if uid_substitutions is present, perform uid_substitutions.  Even if the
      tag doesn't have a VR of UI, if it has a value which matches a <from_uid>
      change it to <to_uid>.
   2) if uid_root_transform is present, perform uid_substitutions.  Even if the
      tag doesn't have a VR of UI, if it has a value which matches a <from_uid>
      change it to <to_uid>.
   3) Then perform operations in order specified.  The same tag may be edited
      multiple times.  The last edit wins.  Caveat usor.

EOF
if($#ARGV == 0 && ($ARGV[0] eq "-h")){
  print $help;
  exit;
}

my $edits = fd_retrieve(\*STDIN);

# apply_edits never dies: a malformed file comes back as Status => "Error",
# which is exactly what the callers already branch on.
my $results = Posda::EditFile::apply_edits(
  $edits->{from_file}, $edits->{to_file}, $edits);

# The original reported from_file even on failure, so preserve that.
$results->{from_file} = $edits->{from_file}
  unless exists $results->{from_file};

store_fd($results, \*STDOUT);
exit;
