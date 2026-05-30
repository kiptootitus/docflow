import { Fragment as _Fragment, jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
function ProtectedRoute({ children }) {
    const { isAuthenticated } = useAuthStore();
    return isAuthenticated ? _jsx(_Fragment, { children: children }) : _jsx(Navigate, { to: "/login", replace: true });
}
// Get Google Client ID from environment variables
const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
export default function App() {
    return (_jsx(QueryClientProvider, { client: queryClient, children: _jsxs(GoogleOAuthProvider, { clientId: googleClientId || "13570999136-57i88iqqjsq5vv16339i5jecp1eqvroh.apps.googleusercontent.com", children: [_jsx(BrowserRouter, { children: _jsxs(Routes, { children: [_jsx(Route, { path: "/login", element: _jsx(LoginPage, {}) }), _jsx(Route, { path: "/register", element: _jsx(RegisterPage, {}) }), _jsx(Route, { path: "/forgot-password", element: _jsx(ForgotPasswordPage, {}) }), _jsx(Route, { path: "/password-reset/confirm/:uid/:token", element: _jsx(PasswordResetConfirmPage, {}) }), _jsx(Route, { path: "/portal/:token", element: _jsx(ClientPortalPage, {}) }), _jsxs(Route, { path: "/", element: _jsx(ProtectedRoute, { children: _jsx(AppLayout, {}) }), children: [_jsx(Route, { index: true, element: _jsx(Navigate, { to: "/dashboard", replace: true }) }), _jsx(Route, { path: "dashboard", element: _jsx(DashboardPage, {}) }), _jsx(Route, { path: "invoices", element: _jsx(InvoicesPage, {}) }), _jsx(Route, { path: "invoices/new", element: _jsx(InvoiceEditorPage, {}) }), _jsx(Route, { path: "invoices/:id/edit", element: _jsx(InvoiceEditorPage, {}) }), _jsx(Route, { path: "quotations", element: _jsx(QuotationsPage, {}) }), _jsx(Route, { path: "quotations/new", element: _jsx(QuotationEditorPage, {}) }), _jsx(Route, { path: "quotations/:id/edit", element: _jsx(QuotationEditorPage, {}) }), _jsx(Route, { path: "contracts", element: _jsx(ContractsPage, {}) }), _jsx(Route, { path: "clients", element: _jsx(ClientsPage, {}) }), _jsx(Route, { path: "ai-review", element: _jsx(AiReviewPage, {}) }), _jsx(Route, { path: "settings", element: _jsx(SettingsPage, {}) }), _jsx(Route, { path: "billing", element: _jsx(BillingPage, {}) })] }), _jsx(Route, { path: "*", element: _jsx(Navigate, { to: "/dashboard", replace: true }) })] }) }), _jsx(ReactQueryDevtools, { initialIsOpen: false })] }) }));
}
