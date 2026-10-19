import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useSWRConfig } from "swr";
import { logout } from "../api/abc";
import { useMe } from "../auth/AuthGate";

const NAV = [
  ["/activities", "Activity"],
  ["/workflow", "Workflow"],
  ["/queries", "Queries"],
  ["/inbox", "Inbox"],
  ["/upload", "Upload"],
  ["/upload-to-event", "Upload To Event"],
  ["/download", "Download"],
  ["/background", "Show Background"],
] as const;

export function AppShell() {
  const me = useMe();
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();

  async function signOut() {
    await logout();
    await mutate(() => true, undefined, { revalidate: false });
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-gray-300 bg-gray-100 px-4 py-2">
        <span className="mr-2 font-semibold">Activity Based Curation</span>
        <nav className="flex flex-wrap gap-x-3 text-sm">
          {NAV.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                isActive ? "font-semibold text-blue-800 underline" : "text-blue-700"
              }
            >
              {label}
            </NavLink>
          ))}
          {me.launchable_apps.includes("UserAdmin") && (
            <NavLink to="/admin" className="text-blue-700">
              Admin
            </NavLink>
          )}
        </nav>
        <span className="ml-auto text-sm text-gray-600">
          {me.username}{" "}
          <button type="button" className="btn ml-2" onClick={signOut}>
            Sign out
          </button>
        </span>
      </header>
      <main className="p-4">
        <Outlet />
      </main>
    </div>
  );
}
