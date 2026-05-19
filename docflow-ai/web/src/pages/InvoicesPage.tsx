import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Send, Copy, Trash2, ExternalLink, FileText } from "lucide-react";
import { invoicesApi } from "@/lib/api";
import { formatCurrency, formatDate, STATUS_COLORS, cn } from "@/lib/utils";

export default function InvoicesPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["invoices", search, statusFilter],
    queryFn: () => invoicesApi.list({ ...(search && { search }), ...(statusFilter && { status: statusFilter }) }),
  });

  const sendMutation = useMutation({
    mutationFn: (id: string) => invoicesApi.sendEmail(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const paidMutation = useMutation({
    mutationFn: (id: string) => invoicesApi.markPaid(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const dupMutation = useMutation({
    mutationFn: (id: string) => invoicesApi.duplicate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => invoicesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const invoices = data?.data?.results ?? [];

  return (
    <div className="p-4 sm:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Invoices</h1>
          <p className="text-gray-500 text-sm mt-0.5">{data?.data?.count ?? 0} total</p>
        </div>
        <Link to="/invoices/new" className="flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors w-full sm:w-auto shadow-sm">
          <Plus className="w-4 h-4" /> New Invoice
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6">
        <div className="relative flex-1 max-w-none sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search invoices..."
            className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white h-9 sm:h-auto"
        >
          <option value="">All statuses</option>
          {["draft","sent","viewed","paid","overdue","cancelled"].map(s => (
            <option key={s} value={s} className="capitalize">{s}</option>
          ))}
        </select>
      </div>

      {/* Table Canvas with Scroll Container Wrapper */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] table-auto">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50">
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Invoice</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Client</th>
                <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Amount</th>
                <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Due</th>
                <th className="px-6 py-3 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {isLoading && (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-400">Loading...</td></tr>
              )}
              {!isLoading && invoices.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-400">No invoices found.</td></tr>
              )}
              {invoices.map((inv) => (
                <tr key={inv.id} className="hover:bg-gray-50/80 transition-colors group">
                  <td className="px-6 py-4">
                    <Link to={`/invoices/${inv.id}/edit`} className="text-sm font-medium text-indigo-600 hover:underline">
                      {inv.number}
                    </Link>
                    <p className="text-xs text-gray-400 mt-0.5">{formatDate(inv.created_at)}</p>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700 truncate max-w-[160px]">
                    {inv.client_name ?? <span className="text-gray-300">—</span>}
                  </td>
                  <td className="px-6 py-4 text-right text-sm font-semibold text-gray-900">
                    {formatCurrency(inv.total_amount, inv.currency)}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className={cn("text-xs font-medium px-2.5 py-1 rounded-full capitalize inline-block text-center min-w-[75px]", STATUS_COLORS[inv.status])}>
                      {inv.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {inv.due_date ? formatDate(inv.due_date) : "—"}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity justify-end">
                      {inv.status === "draft" && (
                        <button title="Send" onClick={() => sendMutation.mutate(inv.id)} className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors">
                          <Send className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {inv.status !== "paid" && (
                        <button title="Mark paid" onClick={() => paidMutation.mutate(inv.id)} className="p-1.5 text-gray-400 hover:text-green-600 transition-colors text-xs font-medium">
                          ✓
                        </button>
                      )}
                      <button title="Duplicate" onClick={() => dupMutation.mutate(inv.id)} className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors">
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                      {inv.portal_url && (
                        <a href={inv.portal_url} target="_blank" rel="noreferrer" title="Client portal" className="p-1.5 text-gray-400 hover:text-indigo-600 transition-colors">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      <button title="Delete" onClick={() => { if (confirm("Delete this invoice?")) deleteMutation.mutate(inv.id); }} className="p-1.5 text-gray-400 hover:text-red-500 transition-colors">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}