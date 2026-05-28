import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import type { Invoice } from "@/lib/api";
import { FileText, CreditCard, CheckCircle2, Loader2, AlertTriangle } from "lucide-react";

export default function ClientPortalPage() {
  const { token } = useParams<{ token: string }>();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [isRedirecting, setIsRedirecting] = useState<boolean>(false);

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
        } else {
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
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
          <div className="text-gray-500 text-sm font-medium">Loading secure invoice details...</div>
        </div>
      </div>
    );
  }

  // Error State View Template
  if (error || !invoice) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center bg-white p-8 rounded-2xl border border-gray-100 shadow-md max-w-sm w-full">
          <AlertTriangle className="w-12 h-12 text-amber-500 mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-gray-800">Unable to Load Invoice</h2>
          <p className="text-gray-500 text-sm mt-2 leading-relaxed">
            {error || "This link may have expired or is invalid. Please contact the company directly if you think this is a mistake."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-6 sm:py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">

          {/* Header Area */}
          <div className="bg-indigo-600 px-6 sm:px-8 py-6 text-white">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <h1 className="text-lg sm:text-xl font-bold truncate">Invoice {invoice.number || "N/A"}</h1>
                <p className="text-indigo-200 text-xs sm:text-sm mt-0.5 truncate">
                  From {invoice.company_name || "Your Service Provider"}
                </p>
              </div>
              <span className={cn(
                "text-xs font-semibold px-3 py-1.5 rounded-full capitalize text-center flex-shrink-0 border",
                invoice.status === "paid"
                  ? "bg-green-500/20 text-green-100 border-green-400/30"
                  : "bg-white/20 text-white border-white/10"
              )}>
                {invoice.status || "unpaid"}
              </span>
            </div>
          </div>

          {/* Details Body */}
          <div className="p-5 sm:p-8">
            <div className="grid grid-cols-2 gap-4 sm:gap-6 mb-8">
              <div>
                <p className="text-[10px] sm:text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Issue Date</p>
                <p className="text-xs sm:text-sm text-gray-900 font-medium">
                  {invoice.issue_date ? formatDate(invoice.issue_date) : "—"}
                </p>
              </div>
              {invoice.due_date && (
                <div>
                  <p className="text-[10px] sm:text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Due Date</p>
                  <p className="text-xs sm:text-sm text-indigo-600 font-semibold">
                    {formatDate(invoice.due_date)}
                  </p>
                </div>
              )}
            </div>

            {/* Line Items Grid Table Section */}
            <div className="overflow-x-auto -mx-5 px-5 sm:mx-0 sm:px-0 mb-6">
              <table className="w-full table-auto min-w-[450px]">
                <thead>
                  <tr className="border-b border-gray-200 text-left">
                    <th className="pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider w-3/5">Description</th>
                    <th className="pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider text-center w-1/5">Qty</th>
                    <th className="pb-2.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider text-right w-1/5">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {invoice.line_items && invoice.line_items.length > 0 ? (
                    invoice.line_items.map((item, i) => (
                      <tr key={i} className="border-b border-gray-50/60">
                        <td className="py-3 text-xs sm:text-sm text-gray-700 pr-2 break-words">{item.description}</td>
                        <td className="py-3 text-center text-xs sm:text-sm text-gray-500">{item.quantity}</td>
                        <td className="py-3 text-right text-xs sm:text-sm font-semibold text-gray-900">
                          {formatCurrency(item.amount ?? "0", invoice.currency || "USD")}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={3} className="py-4 text-center text-xs text-gray-400 italic">
                        No items specified on this document.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Aggregated Balance Summary */}
            <div className="flex justify-end">
              <div className="w-full sm:min-w-[240px] sm:w-auto space-y-2 border-t sm:border-t-0 border-gray-100 pt-4 sm:pt-0">
                <div className="flex justify-between text-xs sm:text-sm text-gray-500 gap-4">
                  <span>Subtotal</span>
                  <span className="font-medium text-gray-900">
                    {formatCurrency(invoice.subtotal ?? "0", invoice.currency || "USD")}
                  </span>
                </div>
                {invoice.tax_rate !== undefined && (
                  <div className="flex justify-between text-xs sm:text-sm text-gray-500 gap-4">
                    <span>VAT ({invoice.tax_rate}%)</span>
                    <span className="font-medium text-gray-900">
                      {formatCurrency(invoice.tax_amount ?? "0", invoice.currency || "USD")}
                    </span>
                  </div>
                )}
                <div className="flex justify-between text-sm sm:text-base font-bold border-t border-gray-200 pt-2.5 mt-2 gap-4">
                  <span className="text-gray-900">Total Due</span>
                  <span className="text-indigo-600">
                    {formatCurrency(invoice.total_amount ?? "0", invoice.currency || "USD")}
                  </span>
                </div>
              </div>
            </div>

            {/* Gateway CTA Triggers */}
            {invoice.stripe_payment_link && invoice.status !== "paid" && (
              <div className="mt-8 text-center">
                <a
                  href={invoice.stripe_payment_link}
                  target="_blank"
                  rel="noreferrer"
                  onClick={() => setIsRedirecting(true)}
                  className={cn(
                    "inline-flex items-center justify-center gap-2 bg-indigo-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-indigo-700 transition-colors shadow-sm w-full sm:w-auto text-sm sm:text-base",
                    isRedirecting && "opacity-60 pointer-events-none"
                  )}
                >
                  <CreditCard className="w-4 h-4 sm:w-5 sm:h-5" />
                  {isRedirecting ? "Connecting Secure Checkout..." : "Pay Invoice Instantly"}
                </a>
              </div>
            )}

            {invoice.status === "paid" && (
              <div className="mt-8 text-center py-4 bg-green-50 rounded-xl border border-green-100/50 px-4 flex items-center justify-center gap-2 max-w-md mx-auto">
                <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0" />
                <p className="text-green-700 font-semibold text-xs sm:text-sm">Payment received — thank you!</p>
              </div>
            )}
          </div>
        </div>

        <p className="text-center text-[10px] sm:text-xs text-gray-400 mt-6 tracking-wide">Powered by DocFlow AI</p>
      </div>
    </div>
  );
}