import { Navigate, Route, Routes } from "react-router-dom";
import { AuthGate } from "./auth/AuthGate";
import { AppShell } from "./components/AppShell";
import { ActivitiesPage } from "./pages/ActivitiesPage";
import { ActivityPage } from "./pages/ActivityPage";
import { HomeRedirect } from "./pages/HomeRedirect";
import { LoginPage } from "./pages/LoginPage";
import { NotYetPage } from "./pages/NotYetPage";
import { QueriesPage } from "./pages/QueriesPage";
import { QueryPage } from "./pages/QueryPage";
import { RunPage } from "./pages/RunPage";

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
        <Route path="/workflow" element={<NotYetPage title="Workflow" phase={3} />} />
        <Route path="/queries" element={<QueriesPage />} />
        <Route path="/queries/:name" element={<QueryPage />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/inbox" element={<NotYetPage title="Inbox" phase={4} />} />
        <Route path="/upload" element={<NotYetPage title="Upload" phase={3} />} />
        <Route
          path="/upload-to-event"
          element={<NotYetPage title="Upload To Event" phase={4} />}
        />
        <Route path="/download" element={<NotYetPage title="Download" phase={4} />} />
        <Route
          path="/background"
          element={<NotYetPage title="Background" phase={4} />}
        />
        <Route path="/admin" element={<NotYetPage title="Admin" phase={5} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
