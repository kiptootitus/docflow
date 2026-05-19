import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Plus, Search, Send, Copy, Trash2, ExternalLink,
  FileText, Sparkles, ArrowRight, Clock, CheckCircle2,
  XCircle, Eye, Printer, ArrowLeft, Phone, Building2
} from "lucide-react";
import { quotationsApi, companiesApi } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import type { Quotation } from "@/lib/api";

const STATUS_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  draft:    { label: "Draft",    color: "bg-slate-100 text-slate-700 ring-slate-600/10",   icon: FileText    },
  sent:     { label: "Sent",     color: "bg-blue-50 text-blue-700 ring-blue-600/10",       icon: Send        },
  viewed:   { label: "Viewed",   color: "bg-indigo-50 text-indigo-700 ring-indigo-600/10", icon: ExternalLink },
  accepted: { label: "Accepted", color: "bg-emerald-50 text-emerald-700 ring-emerald-600/10", icon: CheckCircle2 },
  declined: { label: "Declined", color: "bg-rose-50 text-rose-700 ring-rose-600/10",       icon: XCircle     },
  expired:  { label: "Expired",  color: "bg-amber-50 text-amber-700 ring-amber-600/10",    icon: Clock       },
};

function ExpiryBadge({ expiryDate }: { expiryDate: string | null }) {
  if (!expiryDate) return <span className="text-gray-400 text-xs">—</span>;
  const days = Math.ceil((new Date(expiryDate).getTime() - Date.now()) / 86400000);
  if (days < 0)  return <span className="inline-flex items-center text-[11px] font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md">Expired</span>;
  if (days === 0) return <span className="inline-flex items-center text-[11px] font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">Today</span>;
  if (days <= 3)  return <span className="inline-flex items-center text-[11px] font-semibold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">{days}d left ⏳</span>;
  return <span className="text-xs text-gray-500 font-medium">{formatDate(expiryDate)}</span>;
}

export default function QuotationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showAiModal, setShowAiModal] = useState(false);
  const [convertTarget, setConvertTarget] = useState<Quotation | null>(null);
  const [aiPrefill, setAiPrefill] = useState<Partial<Quotation> | null>(null);
  const [documentViewTarget, setDocumentViewTarget] = useState<any | null>(null);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data, isLoading } = useQuery({
    queryKey: ["quotations", search, statusFilter],
    queryFn: () => quotationsApi.list({ ...(search && { search }), ...(statusFilter && { status: statusFilter }) }),
  });

  const sendMutation = useMutation({ mutationFn: (id: string) => quotationsApi.send(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["quotations"] }) });
  const dupMutation = useMutation({ mutationFn: (id: string) => quotationsApi.duplicate(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["quotations"] }) });
  const deleteMutation = useMutation({ mutationFn: (id: string) => quotationsApi.delete(id), onSuccess: () => qc.invalidateQueries({ queryKey: ["quotations"] }) });

  const quotations = data?.data?.results ?? [];
  const stats = {
    total: data?.data?.count ?? 0,
    accepted: quotations.filter(q => q.status === "accepted").length,
    pending: quotations.filter(q => q.status === "sent" || q.status === "viewed").length,
    totalValue: quotations.reduce((s, q) => s + parseFloat(q.total_amount ?? "0"), 0),
  };

  if (documentViewTarget) {
    const q = documentViewTarget;
    return (
      <div className="p-4 sm:p-8 max-w-4xl mx-auto animate-fade-in bg-gray-50/40 min-h-screen">
        <div className="flex items-center justify-between border-b border-gray-100 pb-4 mb-6 print:hidden">
          <button onClick={() => setDocumentViewTarget(null)} className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900 font-bold transition-colors">
            <ArrowLeft className="w-4 h-4" /> Back to Dashboard
          </button>
          <button onClick={() => window.print()} className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-xs font-bold shadow-xs active:scale-98 transition-all">
            <Printer className="w-4 h-4" /> Save / Print PDF
          </button>
        </div>

        {/* Printable Canvas Sheet Document wrapper */}
        <div className="bg-white rounded-3xl border border-gray-100 p-8 sm:p-16 shadow-sm print:p-0 print:border-none print:shadow-none text-xs sm:text-sm text-gray-700">
          <div className="flex flex-col sm:flex-row justify-between items-start gap-8 border-b border-gray-100 pb-8 mb-8">
            <div className="space-y-3">
              {company?.logo ? (
                <img src={company.logo} alt="Company Logo" className="w-16 h-16 object-contain rounded-2xl border border-gray-100" />
              ) : (
                <div className="w-14 h-14 bg-indigo-600 text-white rounded-2xl flex items-center justify-center font-black text-xl shadow-xs">
                  {company?.name ? company.name[0].toUpperCase() : "D"}
                </div>
              )}
              <div>
                <h2 className="text-base font-bold text-gray-900">{company?.name ?? "DocFlow AI Client"}</h2>
                <p className="text-gray-400 font-medium mt-0.5">{company?.address_line1 || "Mombasa Road, Nairobi"}</p>
                <p className="text-gray-400 font-medium">{company?.email || "billing@docflow.ai"}</p>
              </div>
            </div>
            <div className="text-left sm:text-right space-y-1">
              <h1 className="text-2xl font-black text-indigo-600 tracking-tight uppercase">PROPOSAL QUOTE</h1>
              <p className="font-bold text-gray-900 text-base">{q.number}</p>
              <p className="text-gray-400 font-medium">Issue Date: {formatDate(q.issue_date)}</p>
              <p className="text-indigo-600 font-semibold">Valid Until: {formatDate(q.expiry_date || q.due_date)}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 bg-gray-50/50 p-5 rounded-2xl border border-gray-100/50 mb-8">
            <div>
              <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wide">Client Presentation</p>
              <p className="text-base font-bold text-gray-900 mt-1">
                {q.salutation || "Mr."} {q.client_name || "Unassigned Customer"}
              </p>
              <p className="text-gray-500 font-medium mt-0.5 truncate">{q.title}</p>
            </div>
            <div className="sm:text-right flex flex-col sm:items-end justify-center space-y-1 text-xs text-gray-500">
              {q.client_phone && <p className="flex items-center gap-1.5 font-medium text-gray-700"><Phone className="w-3.5 h-3.5 text-gray-400" /> {q.client_phone}</p>}
              {q.building_address && <p className="flex items-center gap-1.5 font-medium text-gray-700"><Building2 className="w-3.5 h-3.5 text-gray-400" /> {q.building_address}</p>}
            </div>
          </div>

          <table className="w-full text-left border-collapse mb-8">
            <thead>
              <tr className="bg-indigo-600 text-white text-[10px] uppercase tracking-wider font-bold">
                <th className="p-3.5 rounded-tl-xl w-3/5">Line Description Breakdown</th>
                <th className="p-3.5 text-center w-1/5">Qty</th>
                <th className="p-3.5 text-right rounded-tr-xl w-1/5">Total Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 border-b border-gray-100 font-medium text-gray-800">
              {q.line_items?.map((item: any, i: number) => (
                <tr key={i} className="hover:bg-gray-50/40 transition-colors">
                  <td className="p-3.5 text-gray-700">{item.description}</td>
                  <td className="p-3.5 text-center text-gray-400 font-mono">{item.quantity}</td>
                  <td className="p-3.5 text-right text-gray-900 font-bold">
                    {formatCurrency(parseFloat(item.amount || String(item.quantity * item.unit_price)), q.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex justify-end">
            <div className="w-full sm:w-72 space-y-2.5 text-right border-t border-gray-50 pt-4">
              <div className="flex justify-between text-gray-400 font-medium">
                <span>Subtotal</span>
                <span className="text-gray-900">{formatCurrency(parseFloat(q.subtotal || "0"), q.currency)}</span>
              </div>
              <div className="flex justify-between text-gray-400 font-medium">
                <span>VAT ({q.tax_rate}%)</span>
                <span className="text-gray-900">{formatCurrency(parseFloat(q.tax_amount || "0"), q.currency)}</span>
              </div>
              {parseFloat(q.discount_amount || "0") > 0 && (
                <div className="flex justify-between text-rose-500 font-semibold">
                  <span>Discount subtraction</span>
                  <span>-{formatCurrency(parseFloat(q.discount_amount), q.currency)}</span>
                </div>
              )}
              <div className="flex justify-between text-base font-black text-gray-900 border-t-2 border-gray-100 pt-3 mt-2">
                <span>Total Balance Due</span>
                <span className="text-indigo-600 tracking-wide">{formatCurrency(parseFloat(q.total_amount || "0"), q.currency)}</span>
              </div>
            </div>
          </div>

          {q.notes && (
            <div className="mt-12 p-4 bg-gray-50 rounded-xl border border-gray-100 text-gray-400 text-xs font-medium leading-relaxed">
              <strong>Notes / Conditions:</strong> {q.notes}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-8 bg-gray-50/30 min-h-screen print:hidden">
      {/* Brand Control Headers */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Quotations Pipeline</h1>
          <p className="text-gray-400 text-xs sm:text-sm mt-0.5">{stats.total} total proposals generated workspace catalog</p>
        </div>
        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          <Link to="/quotations/new" className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2.5 rounded-xl text-sm font-semibold shadow-sm transition-all active:scale-98">
            <Plus className="w-4 h-4" /> New Proposal
          </Link>
        </div>
      </div>

      {/* Grid Stats cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Quotes",   value: stats.total,                                                    color: "bg-white border-gray-100 text-gray-900 shadow-xs" },
          { label: "Awaiting Reply", value: stats.pending,                                                  color: "bg-white border-gray-100 text-blue-600 shadow-xs" },
          { label: "Accepted",       value: stats.accepted,                                                 color: "bg-white border-gray-100 text-emerald-600 shadow-xs" },
          { label: "Pipeline Value", value: formatCurrency(stats.totalValue, company?.default_currency ?? "KES"), color: "bg-gradient-to-br from-indigo-600 to-violet-600 text-white border-transparent shadow-md" },
        ].map((s, idx) => (
          <div key={idx} className={cn("rounded-2xl p-5 border transition-all hover:scale-[1.01]", s.color)}>
            <p className={cn("text-[10px] sm:text-xs font-bold uppercase tracking-wider opacity-70 truncate", idx === 3 && "text-indigo-100")}>{s.label}</p>
            <p className="text-xl sm:text-2xl font-black mt-1.5 truncate tracking-tight">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Filtering inputs controls */}
      <div className="flex flex-col sm:flex-row gap-3 mb-6 bg-white p-4 rounded-xl border border-gray-100 shadow-xs">
        <div className="relative flex-1 max-w-none sm:max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search proposals..." className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 bg-gray-50/50" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-500 bg-white h-9 sm:h-auto font-medium text-gray-600">
          <option value="">All statuses</option>
          {Object.entries(STATUS_META).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
      </div>

      {/* Main Presentation Table Container */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[750px] table-auto border-collapse">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/50 text-left text-gray-400 font-bold text-[11px] uppercase tracking-wider">
                <th className="px-6 py-4">Quote Identification</th>
                <th className="px-6 py-4">Client Representative</th>
                <th className="px-6 py-4 text-right">Valuation</th>
                <th className="px-6 py-4 text-center">Status</th>
                <th className="px-6 py-4">Expires</th>
                <th className="px-6 py-4 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 font-medium text-gray-700">
              {isLoading && (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-400 animate-pulse">Loading workspace stream...</td></tr>
              )}

              {!isLoading && quotations.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center text-gray-400 text-sm font-medium">
                    No quotations generated yet catalog listings view.
                  </td>
                </tr>
              )}

              {quotations.map((q) => {
                const sm = STATUS_META[q.status] ?? STATUS_META.draft;
                const StatusIcon = sm.icon;
                return (
                  <tr key={q.id} className="hover:bg-gray-50/40 transition-colors group">
                    <td className="px-6 py-4">
                      <button type="button" onClick={() => setDocumentViewTarget(q)} className="text-sm font-bold text-indigo-600 hover:underline inline-flex items-center gap-1">
                        {q.number} <Eye className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </button>
                      <p className="text-xs text-gray-400 mt-0.5 max-w-[180px] truncate">{q.title}</p>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900 font-bold">
                      {q.salutation || "Mr."} {q.client_name ?? <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-6 py-4 text-right text-sm font-black text-gray-900">
                      {formatCurrency(q.total_amount, q.currency)}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={cn("inline-flex items-center gap-1 text-[11px] font-bold px-3 py-1 rounded-full ring-1 ring-inset capitalize min-w-[90px] justify-center", sm.color)}>
                        <StatusIcon className="w-3 h-3 flex-shrink-0" /> {sm.label}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <ExpiryBadge expiryDate={q.expiry_date} />
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-0.5 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity justify-end">
                        <button type="button" title="View Document" onClick={() => setDocumentViewTarget(q)} className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-gray-50">
                          <Eye className="w-4 h-4" />
                        </button>
                        <button type="button" title="Delete" onClick={() => { if (confirm("Delete this quotation?")) deleteMutation.mutate(q.id); }} className="p-1.5 text-gray-400 hover:text-red-500 rounded-lg hover:bg-red-50">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
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