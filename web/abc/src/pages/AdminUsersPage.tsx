import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { createAdminUser, deleteAdminUser, patchAdminUser, paths, putAdminPermissions } from "../api/abc";
import { ApiError } from "../api/client";
import type { AdminUser, PermissionMap } from "../api/types";
import { useMe } from "../auth/AuthGate";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : String(err);
}

/** The UserAdmin app: accounts, their app permissions and passwords. */
export function AdminUsersPage() {
  const me = useMe();
  const users = useSWR<AdminUser[]>(paths.adminUsers);
  const [selected, setSelected] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  if (users.error instanceof ApiError && users.error.status === 403) {
    return <p className="text-red-700">You may not administer users.</p>;
  }
  if (users.error) return <p className="text-red-700">{String(users.error)}</p>;
  if (!users.data) return <p className="text-gray-500">Loading…</p>;

  async function remove(user: AdminUser) {
    if (!window.confirm(`You are about to delete the user ${user.user_name}. This operation CANNOT be undone.`)) return;
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
      <h1 className="text-xl font-semibold">Users</h1>
      <p className="my-2 rounded bg-blue-50 p-2 text-sm text-blue-900">
        Click on a user's name to edit their app permissions and password. Click the <b>X</b> to the right of the user to delete them.
      </p>
      {notice && <p className="text-sm text-green-800">{notice}</p>}
      {failure && <p className="text-sm text-red-700">{failure}</p>}
      <div className="flex flex-wrap gap-8">
        <table className="table-grid w-auto">
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
            {users.data.map((user) => (
              <tr key={user.user_id}>
                <td>
                  <button type="button" className={selected === user.user_name ? "btn-primary" : "btn"} onClick={() => setSelected(user.user_name)}>
                    {user.user_name}
                  </button>
                </td>
                <td>{user.full_name}</td>
                <td>{user.email}</td>
                <td>{user.disabled ? <span className="text-red-700">disabled</span> : "active"}</td>
                <td>
                  <button
                    type="button"
                    className="btn border-red-400 text-red-700"
                    disabled={user.user_name === me.username}
                    onClick={() => remove(user)}
                    title="Delete this user"
                  >
                    X
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="min-w-96 flex-1">
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
    <form onSubmit={submit} className="flex flex-col gap-2 text-sm">
      <h2 className="font-semibold">Add new user</h2>
      <input className="input" placeholder="Username" autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
      <input className="input" placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
      <input className="input" placeholder="Email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="input" placeholder="Password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      {failure && <p className="text-red-700">{failure}</p>}
      <button type="submit" className="btn-primary self-start" disabled={!name.trim() || !password}>
        Create
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
    <div className="text-sm">
      <h2 className="font-semibold">Editing User: {user.user_name}</h2>
      <p className="my-2 rounded bg-blue-50 p-2 text-blue-900">
        Toggle permissions by clicking them. <b>launch</b> is required for the user to use an app. Giving a user UserAdmin launch lets them modify these settings.
      </p>
      {failure && <p className="text-red-700">{failure}</p>}
      <h3 className="mt-2 font-semibold">Permissions</h3>
      {!current ? (
        <p className="text-gray-500">Loading…</p>
      ) : (
        <table className="table-grid w-auto">
          <thead>
            <tr>
              <th>App</th>
              <th>Permissions</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(current).map(([app, names]) => (
              <tr key={app}>
                <td>{app}</td>
                <td className="space-x-1">
                  {Object.entries(names).map(([name, granted]) => (
                    <button
                      key={name}
                      type="button"
                      className={granted ? "btn-primary" : "btn"}
                      aria-pressed={granted}
                      onClick={() => toggle(app, name)}
                    >
                      {name}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button type="button" className="btn-primary mt-2" disabled={draft === null} onClick={savePermissions}>
        Assign Permissions
      </button>
      <h3 className="mt-4 font-semibold">Details</h3>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col">
          Full name
          <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </label>
        <label className="flex flex-col">
          Email
          <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <button type="button" className="btn" onClick={() => saveDetails({ full_name: fullName, email: email || null }, "Details saved.")}>
          Save details
        </button>
        <button
          type="button"
          className="btn"
          disabled={isSelf}
          onClick={() => saveDetails({ disabled: !user.disabled }, user.disabled ? "Account enabled." : "Account disabled.")}
        >
          {user.disabled ? "Enable account" : "Disable account"}
        </button>
      </div>
      <h3 className="mt-4 font-semibold">Password</h3>
      <p className="text-gray-600">Passwords are stored hashed and cannot be displayed. You may change the user's password here at any time.</p>
      <div className="flex items-end gap-2">
        <input className="input" type="password" placeholder="New Password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <button
          type="button"
          className="btn border-orange-400"
          disabled={!password}
          onClick={() => saveDetails({ password }, "Password changed.").then(() => setPassword(""))}
        >
          Change Password
        </button>
      </div>
    </div>
  );
}
