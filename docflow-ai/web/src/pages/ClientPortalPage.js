import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import { CreditCard, CheckCircle2, Loader2, AlertTriangle } from "lucide-react";
export default function ClientPortalPage() {
    const { token } = useParams();
    const [invoice, setInvoice] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [isRedirecting, setIsRedirecting] = useState(false);
    useEffect(() => {
        if (!token) {
            setError("Invalid access token wrapper provided.");
            setLoading(false);
            return;
        }
        // Isolate client portal endpoint fetches so they don't break on company-loading limits
        api.get(`/portal/invoice/${token}/`)
            .then((res) => {
            // Fallback structures to handle different formats safely
            const invoiceData = res.data?.data ?? res.data;
            if (invoiceData) {
                setInvoice(invoiceData);
            }
            else {
                setError("Invoice payload came back empty.");
            }
        })
            .catch((err) => {
            console.error("Portal fetch exception error:", err);
            const backendErrorMessage = err.response?.data?.detail || err.response?.data?.error;
            setError(backendErrorMessage ?? "Invoice not found, or link has expired.");
        })
            .finally(() => {
            setLoading(false);
        });
    }, [token]);
    // Loading State UI Context Wrapper
    if (loading) {
        return (_jsx("div", { className: "min-h-screen bg-gray-50 flex items-center justify-center p-4", children: _jsxs("div", { className: "flex flex-col items-center gap-3", children: [_jsx(Loader2, { className: "w-8 h-8 text-indigo-600 animate-spin" }), _jsx("div", { className: "text-gray-500 text-sm font-medium", children: "Loading secure invoice details..." })] }) }));
    }
    // Error State View Template
    if (error || !invoice) {
        return (_jsx("div", { className: "min-h-screen bg-gray-50 flex items-center justify-center p-4", children: _jsxs("div", { className: "text-center bg-white p-8 rounded-2xl border border-gray-100 shadow-md max-w-sm w-full", children: [_jsx(AlertTriangle, { className: "w-12 h-12 text-amber-500 mx-auto mb-3" }), _jsx("h2", { className: "text-lg font-semibold text-gray-800", children: "Unable to Load Invoice" }), _jsx("p", { className: "text-gray-500 text-sm mt-2 leading-relaxed", children: error || "This link may have expired or is invalid. Please contact the company directly if you think this is a mistake." })] }) }));
    }
    return (_jsx("div", { className: "min-h-screen bg-gray-50 py-6 sm:py-12 px-4", children: _jsxs("div", { className: "max-w-2xl mx-auto", children: [_jsxs("div", { className: "bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden", children: [_jsx("div", { className: "bg-indigo-600 px-6 sm:px-8 py-6 text-white", children: _jsxs("div", { className: "flex items-center justify-between gap-4", children: [_jsxs("div", { className: "min-w-0", children: [_jsxs("h1", { className: "text-lg sm:text-xl font-bold truncate", children: ["Invoice ", invoice.number || "N/A"] }), _jsxs("p", { className: "text-indigo-200 text-xs sm:text-sm mt-0.5 truncate", children: ["From ", invoice.company_name || "Your Service Provider"] })] }), _jsx("span", { className: cn("text-xs font-semibold px-3 py-1.5 rounded-full capitalize text-center flex-shrink-0 border", invoice.status === "paid"
                                            ? "bg-green-500/20 text-green-100 border-green-400/30"
                                            : "bg-white/20 text-white border-white/10"), children: invoice.status || "unpaid" })] }) }), _jsxs("div", { className: "p-5 sm:p-8", children: [_jsxs("div", { className: "grid grid-cols-2 gap-4 sm:gap-6 mb-8", children: [_jsxs("div", { children: [_jsx("p", { className: "text-[10px] sm:text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1", children: "Issue Date" }), _jsx("p", { className: "text-xs sm:text-sm text-gray-900 font-medium", children: invoice.issue_date ? formatDate(invoice.issue_date) : "—" })] }), invoice.due_date && (_jsxs("div", { children: [_jsx("p", { className: "text-[10px] sm:text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1", children: "Due Date" }), _jsx("p", { className: "text-xs sm:text-sm text-indigo-600 font-semibold", children: formatDate(invoice.due_date) })] }))] }), _jsx("div", { className: "overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0 mb-6", children: _jsxs("table", { className: "w-full table-auto min-w-[450px]", children: [_jsx("thead", { children: _jsxs("tr", { className: "border-b border-gray-200 text-left", children: [_jsx("th", { className: "pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider w-3/5", children: "Description" }), _jsx("th", { className: "pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider text-center w-1/5", children: "Qty" }), _jsx("th", { className: "pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider text-right w-1/5", children: "Amount" })] }) }), _jsx("tbody", { className: "divide-y divide-gray-100", children: invoice.line_items && invoice.line_items.length > 0 ? (invoice.line_items.map((item, i) => (_jsxs("tr", { className: "border-b border-gray-50/60", children: [_jsx("td", { className: "py-3 text-xs sm:text-sm text-gray-700 pr-2 break-words", children: item.description }), _jsx("td", { className: "py-3 text-center text-xs sm:text-sm text-gray-500", children: item.quantity }), _jsx("td", { className: "py-3 text-right text-xs sm:text-sm font-semibold text-gray-900", children: formatCurrency(item.amount ?? "0", invoice.currency || "USD") })] }, i)))) : (_jsx("tr", { children: _jsx("td", { colSpan: 3, className: "py-4 text-center text-xs text-gray-400 italic", children: "No items specified on this document." }) })) })] }) }), _jsx("div", { className: "flex justify-end", children: _jsxs("div", { className: "w-full sm:min-w-[240px] sm:w-auto space-y-2 border-t sm:border-t-0 border-gray-100 pt-4 sm:pt-0", children: [_jsxs("div", { className: "flex justify-between text-xs sm:text-sm text-gray-500 gap-4", children: [_jsx("span", { children: "Subtotal" }), _jsx("span", { className: "font-medium text-gray-900", children: formatCurrency(invoice.subtotal ?? "0", invoice.currency || "USD") })] }), invoice.tax_rate !== undefined && (_jsxs("div", { className: "flex justify-between text-xs sm:text-sm text-gray-500 gap-4", children: [_jsxs("span", { children: ["VAT (", invoice.tax_rate, "%)"] }), _jsx("span", { className: "font-medium text-gray-900", children: formatCurrency(invoice.tax_amount ?? "0", invoice.currency || "USD") })] })), _jsxs("div", { className: "flex justify-between text-sm sm:text-base font-bold border-t border-gray-200 pt-2.5 mt-2 gap-4", children: [_jsx("span", { className: "text-gray-900", children: "Total Due" }), _jsx("span", { className: "text-indigo-600", children: formatCurrency(invoice.total_amount ?? "0", invoice.currency || "USD") })] })] }) }), invoice.stripe_payment_link && invoice.status !== "paid" && (_jsx("div", { className: "mt-8 text-center", children: _jsxs("a", { href: invoice.stripe_payment_link, target: "_blank", rel: "noreferrer", onClick: () => setIsRedirecting(true), className: cn("inline-flex items-center justify-center gap-2 bg-indigo-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-indigo-700 transition-colors shadow-sm w-full sm:w-auto text-sm sm:text-base", isRedirecting && "opacity-60 pointer-events-none"), children: [_jsx(CreditCard, { className: "w-4 h-4 sm:w-5 sm:h-5" }), isRedirecting ? "Connecting Secure Checkout..." : "Pay Invoice Instantly"] }) })), invoice.status === "paid" && (_jsxs("div", { className: "mt-8 text-center py-4 bg-green-50 rounded-xl border border-green-100/50 px-4 flex items-center justify-center gap-2 max-w-md mx-auto", children: [_jsx(CheckCircle2, { className: "w-5 h-5 text-green-600 flex-shrink-0" }), _jsx("p", { className: "text-green-700 font-semibold text-xs sm:text-sm", children: "Payment received \u2014 thank you!" })] }))] })] }), _jsx("p", { className: "text-center text-[10px] sm:text-xs text-gray-400 mt-6 tracking-wide", children: "Powered by DocFlow AI" })] }) }));
}
