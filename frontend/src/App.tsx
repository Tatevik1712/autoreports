import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useAuthStore } from "@/store/authStore";
import { ProtectedRoute, AdminRoute } from "@/components/layout/ProtectedRoute";
import AppLayout from "@/components/layout/AppLayout";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import FilesPage from "@/pages/FilesPage";
import NewReportPage from "@/pages/NewReportPage";
import ReportsListPage from "@/pages/ReportsListPage";
import ReportDetailPage from "@/pages/ReportDetailPage";
import TemplatesPage from "@/pages/TemplatesPage";
import AdminTemplatesPage from "@/pages/AdminTemplatesPage";
import AdminReportsPage from "@/pages/AdminReportsPage";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function RootRedirect() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return <Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />;
}

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<LoginPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/files" element={<FilesPage />} />
              <Route path="/reports" element={<ReportsListPage />} />
              <Route path="/reports/new" element={<NewReportPage />} />
              <Route path="/reports/:id" element={<ReportDetailPage />} />
              <Route path="/templates" element={<TemplatesPage />} />
            </Route>
          </Route>

          <Route element={<AdminRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/admin/templates" element={<AdminTemplatesPage />} />
              <Route path="/admin/reports" element={<AdminReportsPage />} />
            </Route>
          </Route>

          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
