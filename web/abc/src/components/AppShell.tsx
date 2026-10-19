import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import useSWR, { useSWRConfig } from "swr";
import { logout, paths } from "../api/abc";
import type { Activity } from "../api/types";
import { useMe } from "../auth/AuthGate";
import { useCurrentActivity } from "../hooks/useCurrentActivity";

const NAV: readonly { to: string; label: string; title: string }[] = [
  { to: "/activities", label: "Activity", title: "The selected activity: its timeline and running tasks" },
  { to: "/workflow", label: "Workflow", title: "Curation steps and the operations for each" },
  { to: "/queries", label: "Queries", title: "Run saved queries and see their results" },
  { to: "/inbox", label: "Inbox", title: "Reports from finished operations" },
  { to: "/upload", label: "Upload", title: "Upload spreadsheets and chain them to operations" },
  { to: "/upload-to-event", label: "Upload Data", title: "Upload files into an import event" },
  { to: "/download", label: "Download", title: "Directories prepared for download" },
  { to: "/background", label: "Background", title: "Every background process and its status" },
];

export function AppShell() {
  const me = useMe();
  const navigate = useNavigate();
  const { mutate } = useSWRConfig();
  const unread = useSWR<{ unread: number }>(paths.inboxUnread, { refreshInterval: 10000 });
  const unreadCount = unread.data?.unread ?? 0;

  async function signOut() {
    await logout();
    await mutate(() => true, undefined, { revalidate: false });
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5">
          <Link to="/" className="mr-2 flex items-center gap-2 font-semibold tracking-tight text-slate-900">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-blue-600 text-xs font-bold text-white">
              ABC
            </span>
            <span className="hidden sm:inline">Activity Based Curation</span>
          </Link>
          <nav className="flex flex-wrap gap-0.5" aria-label="Main">
            {NAV.map((item) => (
              <NavItem key={item.to} {...item} badge={item.to === "/inbox" ? unreadCount : 0} />
            ))}
            {me.launchable_apps.includes("UserAdmin") && (
              <NavItem to="/admin" label="Admin" title="User accounts and permissions" badge={0} />
            )}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <CurrentActivityChip />
            <span className="text-slate-600" title={me.full_name ?? me.username}>
              {me.username}
            </span>
            <button type="button" className="btn btn-sm" onClick={signOut}>
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="flex-1 px-4 py-4">
        <Outlet />
      </main>
    </div>
  );
}

function NavItem({ to, label, title, badge }: { to: string; label: string; title: string; badge: number }) {
  return (
    <NavLink
      to={to}
      title={title}
      className={({ isActive }) =>
        `inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm font-medium transition-colors ${
          isActive ? "bg-blue-50 text-blue-800" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        }`
      }
    >
      {label}
      {badge > 0 && (
        <span className="rounded-full bg-red-600 px-1.5 text-xs font-semibold leading-5 text-white" title={`${badge} unread`}>
          {badge}
        </span>
      )}
    </NavLink>
  );
}

/** The selected activity, visible on every page since it pre-fills everything. */
function CurrentActivityChip() {
  const { activityId } = useCurrentActivity();
  const activity = useSWR<Activity>(activityId === null ? null : paths.activity(activityId));
  if (activityId === null) {
    return (
      <Link to="/activities" className="badge badge-warning hover:bg-amber-100" title="Queries and operations pre-fill activity_id from the selected activity">
        No activity selected
      </Link>
    );
  }
  const description = activity.data?.brief_description ?? "";
  return (
    <Link
      to={`/activities/${activityId}`}
      className="badge badge-info max-w-xs hover:bg-blue-100"
      title={description ? `Activity ${activityId}: ${description}` : `Activity ${activityId}`}
    >
      <span className="font-semibold">#{activityId}</span>
      {description && <span className="truncate">{description}</span>}
    </Link>
  );
}
