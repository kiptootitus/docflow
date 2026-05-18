import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { formatCurrency, formatDate, cn, STATUS_COLORS } from "@/lib/utils";
import type { Invoice } from "@/lib/api";
import { FileText, CreditCard, ExternalLink } from "lucide-react";

export default function ClientPortalPage() {
  const { token } = useParams();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    // Find invoice by portal token — we need to search for it
    // In real app the URL would be /portal/:invoiceId?token=:token
    // Here we just show a demo view
    setLoading(false);
    setError("Invoice not found or link has expired.");
  }, [token]);

  if (loading) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="text-gray-400">Loading invoice…</div>
    </div>
  );

  if (error || !invoice) return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="text-center">
        <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
        <h2 className="text-lg font-semibold text-gray-700">Invoice not found</h2>
        <p className="text-gray-400 text-sm mt-1">This link may have expired or is invalid.</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="bg-indigo-600 px-8 py-6 text-white">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-xl font-bold">Invoice {invoice.number}</h1>
                <p className="text-indigo-200 text-sm mt-0.5">From your service provider</p>
              </div>
              <span className={cn("text-xs font-semibold px-3 py-1.5 rounded-full bg-white/20 capitalize")}>
                {invoice.status}
              </span>
            </div>
          </div>
          <div className="p-8">
            <div className="grid grid-cols-2 gap-6 mb-8">
              <div>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Issue Date</p>
                <p className="text-sm text-gray-900">{formatDate(invoice.issue_date)}</p>
              </div>
              {invoice.due_date && (
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Due Date</p>
                  <p className="text-sm text-gray-900 font-medium">{formatDate(invoice.due_date)}</p>
                </div>
              )}
            </div>

            <table className="w-full mb-6">
              <thead>
                <tr className="border-b-2 border-gray-100">
                  <th className="text-left pb-2 text-xs font-semibold text-gray-500 uppercase">Description</th>
                  <th className="text-center pb-2 text-xs font-semibold text-gray-500 uppercase">Qty</th>
                  <th className="text-right pb-2 text-xs font-semibold text-gray-500 uppercase">Amount</th>
                </tr>
              </thead>
              <tbody>
                {invoice.line_items.map((item, i) => (
                  <tr key={i} className="border-b border-gray-50">
                    <td className="py-3 text-sm text-gray-700">{item.description}</td>
                    <td className="py-3 text-center text-sm text-gray-500">{item.quantity}</td>
                    <td className="py-3 text-right text-sm font-medium">{formatCurrency(item.amount ?? "0", invoice.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <div className="flex justify-end">
              <div className="min-w-[220px] space-y-2">
                <div className="flex justify-between text-sm"><span className="text-gray-500">Subtotal</span><span>{formatCurrency(invoice.subtotal, invoice.currency)}</span></div>
                <div className="flex justify-between text-sm"><span className="text-gray-500">VAT ({invoice.tax_rate}%)</span><span>{formatCurrency(invoice.tax_amount, invoice.currency)}</span></div>
                <div className="flex justify-between text-base font-bold border-t border-gray-200 pt-2 mt-2">
                  <span>Total Due</span><span className="text-indigo-600">{formatCurrency(invoice.total_amount, invoice.currency)}</span>
                </div>
              </div>
            </div>

            {invoice.stripe_payment_link && invoice.status !== "paid" && (
              <div className="mt-8 text-center">
                <a href={invoice.stripe_payment_link} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-2 bg-indigo-600 text-white px-8 py-3 rounded-xl font-semibold hover:bg-indigo-700 transition-colors">
                  <CreditCard className="w-5 h-5" /> Pay Now
                </a>
              </div>
            )}
            {invoice.status === "paid" && (
              <div className="mt-8 text-center py-4 bg-green-50 rounded-xl">
                <p className="text-green-700 font-semibold">✓ Payment received — thank you!</p>
              </div>
            )}
          </div>
        </div>
        <p className="text-center text-xs text-gray-400 mt-4">Powered by DocFlow AI</p>
      </div>
    </div>
  );
}
