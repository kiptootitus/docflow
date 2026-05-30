import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, FileText, Clock, FileSignature, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { invoicesApi, companiesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { formatCurrency, formatDate, STATUS_COLORS, cn } from "@/lib/utils";
function StatCard({ label, value, icon: Icon, color, }) {
    return (_jsx("div", { className: "bg-white rounded-xl border border-gray-100 p-4 sm:p-6 shadow-sm", children: _jsxs("div", { className: "flex items-center justify-between gap-2", children: [_jsxs("div", { className: "min-w-0", children: [_jsx("p", { className: "text-xs sm:text-sm text-gray-500 font-medium truncate", children: label }), _jsx("p", { className: "text-xl sm:text-2xl font-bold text-gray-900 mt-1 truncate", children: value })] }), _jsx("div", { className: cn("w-10 h-10 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center flex-shrink-0", color), children: _jsx(Icon, { className: "w-5 h-5 sm:w-6 sm:h-6" }) })] }) }));
}
export default function DashboardPage() {
    const { user } = useAuthStore();
    // ── Company ──────────────────────────────────────────────────────────────
    const { data: companiesData } = useQuery({
        queryKey: ["companies"],
        queryFn: () => companiesApi.list(),
    });
    // The backend returns { count, results: Company[] }
    const company = companiesData?.data?.results?.[0];
    // "currency" is the correct field name on the Company model.
    // Falls back to "USD" if no company exists yet.
    const currency = company?.currency ?? "USD";
    // ── Invoices ─────────────────────────────────────────────────────────────
    const { data: invoicesData } = useQuery({
        queryKey: ["invoices", "recent"],
        queryFn: () => invoicesApi.list({ ordering: "-created_at" }),
    });
    const invoices = invoicesData?.data?.results ?? [];
    const paid = invoices.filter((i) => i.status === "paid");
    const pending = invoices.filter((i) => i.status === "sent" || i.status === "viewed");
    const totalRevenue = paid.reduce((sum, i) => sum + parseFloat(i.total_amount || "0"), 0);
    const totalPending = pending.reduce((sum, i) => sum + parseFloat(i.total_amount || "0"), 0);
    return (_jsxs("div", { className: "p-4 sm:p-8", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8", children: [_jsxs("div", { children: [_jsxs("h1", { className: "text-xl sm:text-2xl font-bold text-gray-900", children: ["Welcome back, ", user?.first_name ?? "there", " \uD83D\uDC4B"] }), _jsx("p", { className: "text-sm text-gray-500 mt-1", children: "Here's your business overview" })] }), _jsxs(Link, { to: "/invoices/new", className: "flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors text-sm w-full sm:w-auto shadow-sm", children: [_jsx(Plus, { className: "w-4 h-4" }), "New Invoice"] })] }), _jsxs("div", { className: "grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8", children: [_jsx(StatCard, { label: "Total Revenue", value: formatCurrency(totalRevenue, currency), icon: TrendingUp, color: "bg-green-50 text-green-600" }), _jsx(StatCard, { label: "Invoices Sent", value: invoicesData?.data?.count ?? 0, icon: FileText, color: "bg-blue-50 text-blue-600" }), _jsx(StatCard, { label: "Pending", value: formatCurrency(totalPending, currency), icon: Clock, color: "bg-amber-50 text-amber-600" }), _jsx(StatCard, { label: "Paid Invoices", value: paid.length, icon: FileSignature, color: "bg-indigo-50 text-indigo-600" })] }), _jsxs("div", { className: "bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden", children: [_jsxs("div", { className: "flex items-center justify-between px-4 sm:px-6 py-4 border-b border-gray-100", children: [_jsx("h2", { className: "font-semibold text-gray-900 text-sm sm:text-base", children: "Recent Invoices" }), _jsx(Link, { to: "/invoices", className: "text-sm text-indigo-600 hover:underline font-medium", children: "View all" })] }), _jsxs("div", { className: "divide-y divide-gray-50 overflow-x-auto", children: [invoices.slice(0, 8).map((invoice) => (_jsxs(Link, { to: `/invoices/${invoice.id}`, className: "flex items-center justify-between px-4 sm:px-6 py-4 hover:bg-gray-50 transition-colors min-w-[500px] sm:min-w-0", children: [_jsxs("div", { className: "flex-1 min-w-0", children: [_jsx("p", { className: "text-sm font-medium text-gray-900 truncate", children: invoice.number }), _jsx("p", { className: "text-xs text-gray-500 truncate", children: invoice.client_name ?? "No client" })] }), _jsx("div", { className: "text-right mx-4", children: _jsx("p", { className: "text-sm font-semibold text-gray-900", children: formatCurrency(parseFloat(invoice.total_amount || "0"), invoice.currency) }) }), _jsxs("div", { className: "flex items-center gap-4", children: [_jsx("span", { className: cn("text-[11px] sm:text-xs font-medium px-2.5 py-1 rounded-full capitalize text-center min-w-[70px]", STATUS_COLORS[invoice.status]), children: invoice.status }), _jsx("p", { className: "text-xs text-gray-400 w-20 text-right", children: formatDate(invoice.created_at) })] })] }, invoice.id))), invoices.length === 0 && (_jsxs("div", { className: "px-6 py-12 text-center", children: [_jsx(FileText, { className: "w-10 h-10 text-gray-300 mx-auto mb-3" }), _jsx("p", { className: "text-gray-500 text-sm", children: "No invoices yet." }), _jsx(Link, { to: "/invoices/new", className: "text-sm text-indigo-600 hover:underline mt-1 inline-block", children: "Create your first invoice" })] }))] })] })] }));
}
