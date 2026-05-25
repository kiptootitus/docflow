import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Search, Send, Trash2, FileText, CheckCircle2, XCircle, Eye, Printer, ArrowLeft, Phone, Building2 } from "lucide-react";
import { quotationsApi, companiesApi } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import type { Quotation } from "@/lib/api";

const STATUS_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  draft:    { label: "Draft",    color: "bg-slate-100 text-slate-700 ring-slate-600/10",   icon: FileText    },
  sent:     { label: "Sent",     color: "bg-blue-50 text-blue-700 ring-blue-600/10",       icon: Send        },
  accepted: { label: "Accepted", color: "bg-emerald-50 text-emerald-700 ring-emerald-600/10", icon: CheckCircle2 },
  declined: { label: "Declined", color: "bg-rose-50 text-rose-700 ring-rose-600/10",       icon: XCircle     },
};

function ExpiryBadge({ expiryDate }: { expiryDate: string | null }) {
  if (!expiryDate) return <span className="text-gray-400 text-xs">—</span>;
  const days = Math.ceil((new Date(expiryDate).getTime() - Date.now()) / 86400000);
  if (days < 0)  return <span className="inline-flex items-center text-[11px] font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md">Expired</span>;
  if (days === 0) return <span className="inline-flex items-center text-[11px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">Expires Today</span>;
  return <span className="text-xs text-slate-600 font-semibold">{formatDate(expiryDate)}</span>;
}

export default function QuotationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [documentViewTarget, setDocumentViewTarget] = useState<any | null>(null);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data, isLoading } = useQuery({
    queryKey: ["quotations", search, statusFilter],
    queryFn: () => quotationsApi.list({ ...(search && { search }), ...(statusFilter && { status: statusFilter }) }),
  });

  const deleteMutation = useMutation({ mutationFn: (id: string) => quotationsApi.delete(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["quotations"] }) });

  const quotations = data?.data?.results ?? [];
  const stats = {
    total: data?.data?.count ?? 0,
    accepted: quotations.filter(q => q.status === "accepted").length,
    pending: quotations.filter(q => q.status === "sent").length,
    totalValue: quotations.reduce((s, q) => s + parseFloat(q.total_amount ?? "0"), 0),
  };

  if (documentViewTarget) {
    const q = documentViewTarget;
    return (
      <div className="p-4 sm:p-8 max-w-4xl mx-auto bg-white min-h-screen animate-fade-in print:p-0">
        <div className="flex items-center justify-between border-b border-gray-100 pb-4 mb-6 print:hidden">
          <button onClick={() => setDocumentViewTarget(null)} className="flex items-center gap-2 text-sm text-gray-500 hover:text-slate-900 font-bold transition-colors">
            <ArrowLeft className="w-4 h-4" /> Pipeline Hub
          </button>
          <button onClick={() => window.print()} className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-sm">
            <Printer className="w-4 h-4" /> Print Document
          </button>
        </div>

        <div className="p-6 sm:p-12 text-xs text-slate-700">
          <div className="flex justify-between items-start border-b-2 border-slate-900 pb-6 mb-6">
            <div>
              <h2 className="text-xl font-black text-slate-900 uppercase tracking-tight">{company?.name || "DocFlow Provider"}</h2>
              <p className="text-gray-400 mt-1">{company?.address_line1 || "Mombasa Road, Nairobi Center Building"}</p>
              <p className="text-gray-400">{company?.email}</p>
            </div>
            <div className="text-right">
              <h1 className="text-2xl font-black text-indigo-600 tracking-tight">PROPOSAL QUOTE</h1>
              <p className="font-mono text-sm font-bold text-slate-800 mt-1">{q.number}</p>
              <p className="text-gray-400 text-[10px] font-bold uppercase mt-1">Issued: {formatDate(q.issue_date)} | Valid: {formatDate(q.expiry_date || q.due_date)}</p>
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-100 p-4 rounded-xl mb-6 grid grid-cols-2">
            <div>
              <p className="text-[9px] uppercase font-bold text-gray-400">Client Details</p>
              <p className="text-sm font-bold text-slate-900 mt-0.5">{q.salutation || "Mr."} {q.client_name || "Enterprise Lead Account"}</p>
            </div>
            <div className="text-right text-gray-500 space-y-0.5 self-center">
              {q.client_phone && <p>Phone: {q.client_phone}</p>}
              {q.building_address && <p>Address: {q.building_address}</p>}
            </div>
          </div>

          <table className="w-full text-left border-collapse mb-6">
            <thead>
              <tr className="bg-slate-900 text-white text-[9px] uppercase tracking-wider font-bold">
                <th className="p-3">Task Description</th>
                <th className="p-3 text-center w-1/12">Qty</th>
                <th className="p-3 text-right w-2/12">Unit Price</th>
                <th className="p-3 text-right w-3/12">Total Valuation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 font-medium">
              {q.line_items?.map((item: any, i: number) => (
                <tr key={i} className="text-slate-800 text-[11px]">
                  <td className="p-3 text-slate-700 font-semibold">{item.description}</td>
                  <td className="p-3 text-center text-gray-400 font-mono">{item.quantity}</td>
                  <td className="p-3 text-right text-gray-500 font-mono">{formatCurrency(parseFloat(item.unit_price), q.currency)}</td>
                  <td className="p-3 text-right text-slate-900 font-black">{formatCurrency(parseFloat(item.amount || String(item.quantity * item.unit_price)), q.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex justify-end">
            <div className="w-64 space-y-2 text-right border-t border-slate-100 pt-4 font-medium text-[11px]">
              <div className="flex justify-between text-base font-black text-slate-900 border-t-2 border-slate-900 pt-2.5 mt-1 bg-slate-50 p-2 rounded-lg">
                <span>Total Value</span>
                <span className="text-indigo-600">{formatCurrency(parseFloat(q.total_amount || "0"), q.currency)}</span>
              </div>
            </div>
          </div>

          {q.notes && (
            <div className="mt-8 p-4 bg-gray-50 rounded-xl border border-gray-100 text-gray-400 text-xs font-medium leading-relaxed">
              <strong>Notes / Conditions:</strong> {q.notes}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-8 bg-gray-50/30 min-h-screen print:hidden">

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Quotations Pipeline</h1>
          <p className="text-gray-400 text-xs mt-0.5">{stats.total} total proposals generated workspace catalog</p>
        </div>
        <Link to="/quotations/new" className="flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-xs transition-all">
          <Plus className="w-4 h-4" /> New Proposal
        </Link>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Quotes", value: stats.total, color: "bg-white text-slate-900 border-gray-100 shadow-xs" },
          { label: "Awaiting Reply", value: stats.pending, color: "bg-white text-blue-600 border-gray-100 shadow-xs" },
          { label: "Accepted Deals", value: stats.accepted, color: "bg-white text-emerald-600 border-gray-100 shadow-xs" },
          { label: "Pipeline Worth", value: formatCurrency(stats.totalValue, company?.default_currency ?? "KES"), color: "bg-slate-900 text-white border-transparent shadow-md" },
        ].map((s, idx) => (
          <div key={idx} className={cn("rounded-2xl p-5 border transition-all hover:scale-[1.01]", s.color)}>
            <p className="text-[10px] sm:text-xs font-bold uppercase tracking-wider opacity-70 truncate">{s.label}</p>
            <p className="text-xl sm:text-2xl font-black mt-1.5 truncate tracking-tight">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 mb-6 bg-white p-4 rounded-xl border border-gray-100 shadow-xs">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search proposals..." className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-slate-50/50" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none bg-white font-semibold text-slate-600">
          <option value="">All statuses</option>
          {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] table-auto border-collapse text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-slate-50/60 text-gray-400 font-bold text-[11px] uppercase tracking-wider">
                <th className="px-6 py-4">Identification Index</th>
                <th className="px-6 py-4">Client Representative</th>
                <th className="px-6 py-4 text-right">Total Value</th>
                <th className="px-6 py-4 text-center">Status</th>
                <th className="px-6 py-4">Expires</th>
                <th className="px-6 py-4 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 font-medium text-slate-700">
              {isLoading && (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-400 animate-pulse">Syncing pipeline catalog streams...</td></tr>
              )}
              {!isLoading && quotations.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-16 text-center text-gray-400 text-sm font-medium">No recorded entries found in query filters.</td></tr>
              )}
              {quotations.map((q) => {
                const sm = STATUS_META[q.status] ?? STATUS_META.draft;
                const StatusIcon = sm.icon;
                return (
                  <tr key={q.id} className="hover:bg-slate-50/40 transition-colors group text-xs sm:text-sm">
                    <td className="px-6 py-4">
                      <button type="button" onClick={() => setDocumentViewTarget(q)} className="font-bold text-indigo-600 hover:underline flex items-center gap-1.5">
                        {q.number} <Eye className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                    </td>
                    <td className="px-6 py-4 text-slate-900 font-bold">
                      {q.salutation || "Mr."} {q.client_name || "—"}
                    </td>
                    <td className="px-6 py-4 text-right text-slate-900 font-black">
                      {formatCurrency(q.total_amount, q.currency)}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={cn("inline-flex items-center gap-1 text-[11px] font-bold px-3 py-1 rounded-full ring-1 ring-inset capitalize", sm.color)}>
                        <StatusIcon className="w-3 h-3" /> {sm.label}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <ExpiryBadge expiryDate={q.expiry_date || q.due_date} />
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button type="button" onClick={() => { if (confirm("Remove agreement data?")) deleteMutation.mutate(q.id); }} className="p-1.5 text-gray-400 hover:text-rose-500 rounded-lg hover:bg-rose-50 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
}