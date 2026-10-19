import { Navigate, Route, Routes } from "react-router-dom";
import { AuthGate } from "./auth/AuthGate";
import { AppShell } from "./components/AppShell";
import { ActivitiesPage } from "./pages/ActivitiesPage";
import { ActivityPage } from "./pages/ActivityPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { BackgroundJobsPage } from "./pages/BackgroundJobsPage";
import { DownloadsPage } from "./pages/DownloadsPage";
import { InboxItemPage } from "./pages/InboxItemPage";
import { InboxPage } from "./pages/InboxPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { QueriesPage } from "./pages/QueriesPage";
import { QueryPage } from "./pages/QueryPage";
import { RunPage } from "./pages/RunPage";
import { UploadPage } from "./pages/UploadPage";
import { UploadToEventPage } from "./pages/UploadToEventPage";
import { WorkflowPage } from "./pages/WorkflowPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <AuthGate>
            <AppShell />
          </AuthGate>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route path="/activities" element={<ActivitiesPage />} />
        <Route path="/activities/:activityId" element={<ActivityPage />} />
        <Route path="/workflow" element={<WorkflowPage />} />
        <Route path="/queries" element={<QueriesPage />} />
        <Route path="/queries/:name" element={<QueryPage />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/inbox/:itemId" element={<InboxItemPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/upload-to-event" element={<UploadToEventPage />} />
        <Route path="/download" element={<DownloadsPage />} />
        <Route path="/background" element={<BackgroundJobsPage />} />
        <Route path="/admin" element={<AdminUsersPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
