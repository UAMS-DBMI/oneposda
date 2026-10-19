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
    <main className="mx-auto mt-16 max-w-sm rounded border border-gray-300 p-6">
      <h1 className="mb-4 text-xl font-semibold">Activity Based Curation</h1>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col text-sm">
          Username
          <input
            className="input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
        </label>
        <label className="flex flex-col text-sm">
          Password
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <button type="submit" className="btn-primary self-start" disabled={busy}>
          Sign in
        </button>
      </form>
    </main>
  );
}
