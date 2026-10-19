# ABC parity checklist

Walk this with the Perl GUI (`/posda/`) and the new SPA (`/abc/`) side by
side on the same database, as the same user. Tick each line when the SPA
does what the Perl app did, or note the accepted difference. Differences
already accepted are listed in `notes/abc-gui-replacement-plan.md`
(Status sections).

## Sign-in and session

- [ ] Sign in at `/abc/login`; the same account works in the Perl GUI and
      Mirabelle without signing in again (shared `logintoken`).
- [ ] Sign out clears the session for both GUIs.
- [ ] Ten wrong passwords lock the account for five minutes (new).

## Activities

- [ ] The activity list shows the same open activities, filter works as a
      regex, creating an activity works and selects it.
- [ ] The selected activity survives a reload and a different browser
      (stored in bindings).
- [ ] The activity page shows the same task-status lines (3 s refresh) and
      dismiss works.
- [ ] The timeline lists the same events with the same timepoint ids and
      file counts; "ol" overlaps agree; email and input viewers show the
      same text.
- [ ] Picking a from and a to timepoint and pressing cmp opens
      CompareTimepoints with the same arguments.
- [ ] Third-party URL yes/no and the URL itself round-trip.

## Queries

- [ ] Recent (6) and frequent (20) lists match after running a few queries.
- [ ] Search by args, columns, SQL text and name gives the same names.
- [ ] Workflow groups list the same queries.
- [ ] The argument form pre-fills activity_id, latest timepoint, notify and
      bindings identically; Today/Yesterday/Last 7/Last 30 fill from/to.
- [ ] A foreground run returns the same rows in the same order; cells for
      timestamps, intervals, numerics and booleans look the same (bools are
      1/0).
- [ ] Paging (first row, show, pg-up/pg-dn) agrees; filtered/unfiltered
      counts agree for a regex filter and for a bad-regex literal filter.
- [ ] CSV download: diff the two files after normalising the `when:` line.
- [ ] Pause, resume, abort, dismiss, re-run behave (pause lands within a
      second or a batch).
- [ ] Chained query buttons open the target form with the mapped values.
- [ ] Mirabelle/Kohlrabi links open the same viewer URLs.
- [ ] Query in background queues RunQueryInBackground.pl and the report
      arrives in the inbox.
- [ ] A non-select query asks for confirmation and reports rows affected.
- [ ] Active tab shows a run started from another API worker/replica.

## Operations

For a representative set (include every `special` one and several with
meta-args), compare the Perl popup with the SPA launch dialog:

- [ ] Same argument values and provenance (spreadsheet / current settings /
      bindings / blank).
- [ ] Same expanded command line (except deliberate fixes: every
      occurrence of a placeholder is replaced).
- [ ] Same input lines, head and tail.
- [ ] Outdated warning and "program not found" shown.
- [ ] Start queues the work; the worker runs it; the report appears in the
      inbox and on the timeline.
- [ ] Launch from: workflow button, operation picker, result table button,
      Chain (candidate list), row button, compare timepoints, named upload,
      unnamed upload.

## Upload, inbox, background, download

- [ ] Uploaded CSV and XLSX files import with the same file ids on
      re-upload (digest), chain to the right operation.
- [ ] Inbox list, unread badge, message text with links, dismiss, forward,
      file to activity, operation history.
- [ ] Background list modes and "in last" window; stdout/stderr links.
- [ ] Download page lists the same directories; tar contents match
      `tar -chf`; delete removes the directory.
- [ ] Upload To Event groups files under one import event and closes it.

## Admin

- [ ] User list, create (with inbox row), permissions toggle, password
      change, disable, delete.
- [ ] A user without ActivityBasedCuration launch gets 403 on `/abc`.

## Operations check before decommission

- [ ] `GET /papi/v1/abc/status` on each replica shows runs and spool usage;
      the janitor marks a killed run `lost` within two minutes.
- [ ] Spool directory is on the shared volume on every API pod.
- [ ] `aiomysql` present in the deployed image; MySQL-backed queries run.
