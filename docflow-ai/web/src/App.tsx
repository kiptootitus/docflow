import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { GoogleOAuthProvider } from "@react-oauth/google"; // Add this import
import { useAuthStore } from "@/lib/auth-store";

// Pages
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import PasswordResetConfirmPage from "@/pages/PasswordResetConfirmPage";
import DashboardPage from "@/pages/DashboardPage";
import InvoicesPage from "@/pages/InvoicesPage";
import InvoiceEditorPage from "@/pages/InvoiceEditorPage";
import QuotationsPage from "@/pages/QuotationsPage";
import QuotationEditorPage from "@/pages/QuotationEditorPage";
import ContractsPage from "@/pages/ContractsPage";
import AiReviewPage from "@/pages/AiReviewPage";
import ClientsPage from "@/pages/ClientsPage";
import SettingsPage from "@/pages/SettingsPage";
import BillingPage from "@/pages/BillingPage";
import ClientPortalPage from "@/pages/ClientPortalPage";
import AppLayout from "@/components/layout/AppLayout";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 2,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

// Get Google Client ID from environment variables
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <GoogleOAuthProvider clientId={googleClientId || "13570999136-57i88iqqjsq5vv16339i5jecp1eqvroh.apps.googleusercontent.com"}>
        <BrowserRouter>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/password-reset/confirm/:uid/:token" element={<PasswordResetConfirmPage />} />
            <Route path="/portal/:token" element={<ClientPortalPage />} />

            {/* Protected */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="invoices" element={<InvoicesPage />} />
              <Route path="invoices/new" element={<InvoiceEditorPage />} />
              <Route path="invoices/:id/edit" element={<InvoiceEditorPage />} />
              <Route path="quotations" element={<QuotationsPage />} />
              <Route path="quotations/new" element={<QuotationEditorPage />} />
              <Route path="quotations/:id/edit" element={<QuotationEditorPage />} />
              <Route path="contracts" element={<ContractsPage />} />
              <Route path="clients" element={<ClientsPage />} />
              <Route path="ai-review" element={<AiReviewPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="billing" element={<BillingPage />} />
            </Route>

            {/* Catch-all Global Redirect */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </BrowserRouter>
        <ReactQueryDevtools initialIsOpen={false} />
      </GoogleOAuthProvider>
    </QueryClientProvider>
  );
}