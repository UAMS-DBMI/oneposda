-- user_variable_binding had no key at all, so the Perl GUI could only ever
-- update-then-insert. Deduplicate (one row per user and variable, keeping the
-- most recently inserted) and add the unique index the ABC API's upsert uses.

delete from user_variable_binding older
using user_variable_binding newer
where older.binding_user = newer.binding_user
  and older.bound_variable_name = newer.bound_variable_name
  and older.ctid < newer.ctid;

create unique index if not exists user_variable_binding_user_variable_key
  on user_variable_binding (binding_user, bound_variable_name);
