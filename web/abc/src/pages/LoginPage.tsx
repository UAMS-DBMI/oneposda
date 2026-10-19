import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSWRConfig } from "swr";
import { login, paths } from "../api/abc";
import { ApiError } from "../api/client";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { mutate } = useSWRConfig();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: { pathname: string } } | null)?.from;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      await mutate(paths.me);
      navigate(from?.pathname ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-sm p-6">
        <div className="mb-5 flex items-center gap-3">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-blue-600 text-sm font-bold text-white">
            ABC
          </span>
          <div>
            <h1 className="text-lg">Activity Based Curation</h1>
            <p className="text-xs text-slate-500">Sign in with your Posda account</p>
          </div>
        </div>
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="field">
            <span>Username</span>
            <input
              className="input"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className="notice notice-danger" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="btn-primary mt-1 justify-center py-1.5" disabled={busy || !username || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
