import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, Loader2, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { invoicesApi, companiesApi } from "@/lib/api";
function deriveClients(invoices) {
    const map = new Map();
    for (const inv of invoices) {
        const email = inv.client_email?.trim().toLowerCase() ?? "";
        const name = inv.client_name?.trim() ?? "";
        const key = email || name || inv.id; // fallback to invoice id if both blank
        if (!map.has(key)) {
            map.set(key, {
                key,
                name,
                email,
                phone: "",
                address: "",
                invoiceCount: 0,
                totalBilled: 0,
                currency: inv.currency ?? "USD",
                lastInvoiceId: inv.id,
            });
        }
        const c = map.get(key);
        c.invoiceCount += 1;
        c.totalBilled += parseFloat(inv.total_amount || inv.total || "0");
        c.lastInvoiceId = inv.id; // keep the most recent
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
}
// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function ClientsPage() {
    // Company — needed for the subtitle only
    const { data: companiesData, isLoading: isLoadingCompany } = useQuery({
        queryKey: ["companies"],
        queryFn: () => companiesApi.list(),
    });
    const company = companiesData?.data?.results?.[0];
    // All invoices — fetch a large page so we capture most clients
    const { data: invoicesData, isLoading: isLoadingInvoices } = useQuery({
        queryKey: ["invoices", "all-for-clients"],
        queryFn: () => invoicesApi.list({ page_size: "200", ordering: "-created_at" }),
        enabled: Boolean(company?.id),
    });
    const invoices = invoicesData?.data?.results ?? [];
    const clients = useMemo(() => deriveClients(invoices), [invoices]);
    // ── Loading ──────────────────────────────────────────────────────────────
    if (isLoadingCompany || (company?.id && isLoadingInvoices)) {
        return (_jsxs("div", { className: "min-h-[60vh] flex flex-col items-center justify-center gap-3", children: [_jsx(Loader2, { className: "w-8 h-8 text-indigo-600 animate-spin" }), _jsx("p", { className: "text-gray-500 text-sm font-medium", children: "Loading clients\u2026" })] }));
    }
    // ── No company yet ───────────────────────────────────────────────────────
    if (!company) {
        return (_jsx("div", { className: "p-4 sm:p-8 text-center text-gray-500 text-sm mt-16", children: "Set up your company workspace first before viewing clients." }));
    }
    // ── Main view ────────────────────────────────────────────────────────────
    return (_jsxs("div", { className: "p-4 sm:p-8", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6", children: [_jsxs("div", { children: [_jsx("h1", { className: "text-xl sm:text-2xl font-bold text-gray-900", children: "Clients" }), _jsxs("p", { className: "text-gray-500 text-sm mt-0.5", children: [clients.length, " unique client", clients.length !== 1 ? "s" : "", " from invoices", company?.name ? ` · ${company.name}` : ""] })] }), _jsxs(Link, { to: "/invoices/new", className: "flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors w-full sm:w-auto shadow-sm", children: [_jsx(FileText, { className: "w-4 h-4" }), " New Invoice"] })] }), clients.length > 0 ? (_jsx("div", { className: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4", children: clients.map((c) => (_jsx(Link, { to: `/invoices?client_email=${encodeURIComponent(c.email)}`, className: "bg-white rounded-xl border border-gray-100 p-4 sm:p-5 shadow-sm hover:border-gray-200 hover:shadow-md transition-all", children: _jsxs("div", { className: "flex items-start gap-3", children: [_jsx("div", { className: "w-10 h-10 bg-indigo-50 text-indigo-700 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0 select-none", children: c.name ? c.name[0].toUpperCase() : "?" }), _jsxs("div", { className: "min-w-0 flex-1", children: [_jsx("h3", { className: "font-semibold text-gray-900 text-sm sm:text-base truncate", children: c.name || "Unnamed client" }), c.email && (_jsx("p", { className: "text-xs sm:text-sm text-gray-500 truncate mt-0.5", children: c.email })), _jsxs("div", { className: "flex items-center gap-3 mt-2.5", children: [_jsxs("span", { className: "text-[11px] bg-gray-50 border border-gray-100 text-gray-500 rounded-md px-2 py-0.5", children: [c.invoiceCount, " invoice", c.invoiceCount !== 1 ? "s" : ""] }), _jsx("span", { className: "text-[11px] font-semibold text-indigo-600", children: new Intl.NumberFormat("en", {
                                                    style: "currency",
                                                    currency: c.currency,
                                                    maximumFractionDigits: 0,
                                                }).format(c.totalBilled) })] })] })] }) }, c.key))) })) : (_jsxs("div", { className: "text-center bg-white border border-gray-100 rounded-xl p-12 max-w-md mx-auto shadow-sm mt-4", children: [_jsx(Users, { className: "w-10 h-10 text-gray-300 mx-auto mb-3" }), _jsx("p", { className: "text-gray-500 text-sm font-medium", children: "No clients yet." }), _jsx("p", { className: "text-gray-400 text-xs mt-1", children: "Clients appear here once you create invoices with client details." }), _jsx(Link, { to: "/invoices/new", className: "text-indigo-600 text-sm font-semibold hover:underline mt-3 inline-block", children: "Create your first invoice" })] }))] }));
}
