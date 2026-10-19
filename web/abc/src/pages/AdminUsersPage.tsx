import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { createAdminUser, deleteAdminUser, patchAdminUser, paths, putAdminPermissions } from "../api/abc";
import { ApiError } from "../api/client";
import type { AdminUser, PermissionMap } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { Badge, EmptyState, ErrorMessage, Loading, Notice, PageHeader, errorText } from "../components/ui";

/** The UserAdmin app: accounts, their app permissions and passwords. */
export function AdminUsersPage() {
  const me = useMe();
  const users = useSWR<AdminUser[]>(paths.adminUsers);
  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  if (users.error instanceof ApiError && users.error.status === 403) {
    return <ErrorMessage>You may not administer users.</ErrorMessage>;
  }
  if (users.error) return <ErrorMessage error={users.error} />;
  if (!users.data) return <Loading />;

  const visible = users.data.filter((u) => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return true;
    return [u.user_name, u.full_name, u.email ?? ""].some((v) => v.toLowerCase().includes(needle));
  });

  async function remove(user: AdminUser) {
    if (!window.confirm(`Delete the user ${user.user_name}? This cannot be undone.`)) return;
    setFailure(null);
    try {
      await deleteAdminUser(user.user_name);
      setNotice(`Deleted ${user.user_name}.`);
      if (selected === user.user_name) setSelected(null);
      await users.mutate();
    } catch (err) {
      setFailure(errorText(err));
    }
  }

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Accounts, the apps they may use, and their passwords."
        actions={
          <button type="button" className={selected === null ? "btn-primary" : "btn"} onClick={() => setSelected(null)}>
            New user
          </button>
        }
      />
      {notice && <Notice tone="success" onDismiss={() => setNotice(null)}>{notice}</Notice>}
      {failure && <ErrorMessage>{failure}</ErrorMessage>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div>
          <input
            className="input mb-2 w-72"
            placeholder="Filter users"
            aria-label="Filter users"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div className="table-wrap">
            <table className="table-grid">
              <thead>
                <tr>
                  <th>user</th>
                  <th>full name</th>
                  <th>email</th>
                  <th>status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((user) => (
                  <tr
                    key={user.user_id}
                    className={`row-link ${selected === user.user_name ? "is-selected" : ""}`}
                    onClick={() => setSelected(user.user_name)}
                  >
                    <td className="font-medium">
                      {user.user_name}
                      {user.user_name === me.username && <span className="ml-1 text-xs text-slate-400">(you)</span>}
                    </td>
                    <td>{user.full_name}</td>
                    <td className="text-slate-600">{user.email}</td>
                    <td>{user.disabled ? <Badge tone="danger">disabled</Badge> : <Badge tone="success">active</Badge>}</td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn-danger btn-sm"
                        disabled={user.user_name === me.username}
                        onClick={(e) => {
                          e.stopPropagation();
                          void remove(user);
                        }}
                        title={user.user_name === me.username ? "You cannot delete yourself" : "Delete this user"}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {visible.length === 0 && <EmptyState>No user matches.</EmptyState>}
          </div>
        </div>
        <div>
          {selected ? (
            <EditUser
              key={selected}
              user={users.data.find((u) => u.user_name === selected)!}
              isSelf={selected === me.username}
              onChanged={async (text) => {
                setNotice(text);
                await users.mutate();
              }}
            />
          ) : (
            <NewUserForm
              onCreated={async (user) => {
                setNotice(`Created ${user.user_name}.`);
                await users.mutate();
                setSelected(user.user_name);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function NewUserForm({ onCreated }: { onCreated: (user: AdminUser) => Promise<void> }) {
  const [name, setName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failure, setFailure] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      const user = await createAdminUser({ user_name: name, full_name: fullName, email: email || null, password });
      setName("");
      setFullName("");
      setEmail("");
      setPassword("");
      await onCreated(user);
    } catch (err) {
      setFailure(errorText(err));
    }
  }

  return (
    <form onSubmit={submit} className="card flex flex-col gap-3">
      <h2>New user</h2>
      <p className="text-sm text-slate-500">After creating the account, grant it <b>launch</b> on the apps it may use.</p>
      <label className="field">
        <span>Username</span>
        <input className="input" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field">
        <span>Full name</span>
        <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      </label>
      <label className="field">
        <span>Email</span>
        <input className="input" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="field">
        <span>Password</span>
        <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      {failure && <p className="text-sm text-red-700">{failure}</p>}
      <button type="submit" className="btn-primary self-start" disabled={!name.trim() || !password}>
        Create user
      </button>
    </form>
  );
}

function EditUser({
  user,
  isSelf,
  onChanged,
}: {
  user: AdminUser;
  isSelf: boolean;
  onChanged: (notice: string) => Promise<void>;
}) {
  const perms = useSWR<PermissionMap>(paths.adminUserPermissions(user.user_name));
  const [draft, setDraft] = useState<PermissionMap | null>(null);
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState(user.full_name);
  const [email, setEmail] = useState(user.email ?? "");
  const [failure, setFailure] = useState<string | null>(null);
  const current = draft ?? perms.data;
  const detailsDirty = fullName !== user.full_name || email !== (user.email ?? "");

  function toggle(app: string, name: string) {
    if (!current) return;
    setDraft({ ...current, [app]: { ...current[app], [name]: !current[app][name] } });
  }

  async function savePermissions() {
    if (!current) return;
    setFailure(null);
    const granted = Object.fromEntries(
      Object.entries(current).map(([app, names]) => [app, Object.keys(names).filter((n) => names[n])]),
    );
    try {
      const saved = await putAdminPermissions(user.user_name, granted);
      setDraft(null);
      await perms.mutate(saved, { revalidate: false });
      await onChanged(`Permissions saved for ${user.user_name}.`);
    } catch (err) {
      setFailure(errorText(err));
    }
  }

  async function saveDetails(patch: { full_name?: string; email?: string | null; disabled?: boolean; password?: string }, done: string) {
    setFailure(null);
    try {
      await patchAdminUser(user.user_name, patch);
      await onChanged(done);
    } catch (err) {
      setFailure(errorText(err));
    }
  }

  return (
    <div className="space-y-4">
      <section className="card">
        <div className="mb-2 flex items-center gap-2">
          <h2>{user.user_name}</h2>
          {user.disabled ? <Badge tone="danger">disabled</Badge> : <Badge tone="success">active</Badge>}
          <button
            type="button"
            className="btn btn-sm ml-auto"
            disabled={isSelf}
            title={isSelf ? "You cannot disable yourself" : ""}
            onClick={() => saveDetails({ disabled: !user.disabled }, user.disabled ? "Account enabled." : "Account disabled.")}
          >
            {user.disabled ? "Enable account" : "Disable account"}
          </button>
        </div>
        {failure && <ErrorMessage>{failure}</ErrorMessage>}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="field">
            <span>Full name</span>
            <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </label>
          <label className="field">
            <span>Email</span>
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
        </div>
        <button
          type="button"
          className="btn-primary mt-3"
          disabled={!detailsDirty}
          onClick={() => saveDetails({ full_name: fullName, email: email || null }, "Details saved.")}
        >
          Save details
        </button>
      </section>
      <section className="card">
        <h2 className="mb-1">Permissions</h2>
        <p className="mb-2 text-sm text-slate-500">
          Click a permission to toggle it. <b>launch</b> lets the user open an app; UserAdmin launch lets them edit this page.
        </p>
        {!current ? (
          <Loading />
        ) : (
          <div className="divide-y divide-slate-100">
            {Object.entries(current).map(([app, names]) => (
              <div key={app} className="flex flex-wrap items-center gap-2 py-2">
                <span className="w-48 text-sm font-medium">{app}</span>
                {Object.entries(names).map(([name, granted]) => (
                  <button
                    key={name}
                    type="button"
                    className={granted ? "btn-primary btn-sm" : "btn btn-sm"}
                    aria-pressed={granted}
                    onClick={() => toggle(app, name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
        <div className="toolbar mt-3">
          <button type="button" className="btn-primary" disabled={draft === null} onClick={savePermissions}>
            Save permissions
          </button>
          {draft !== null && (
            <button type="button" className="btn" onClick={() => setDraft(null)}>
              Discard changes
            </button>
          )}
        </div>
      </section>
      <section className="card">
        <h2 className="mb-1">Password</h2>
        <p className="mb-2 text-sm text-slate-500">Passwords are stored hashed and cannot be shown. Set a new one here.</p>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void saveDetails({ password }, "Password changed.").then(() => setPassword(""));
          }}
        >
          <label className="field">
            <span>New password</span>
            <input className="input" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          <button type="submit" className="btn" disabled={!password}>
            Change password
          </button>
        </form>
      </section>
    </div>
  );
}
