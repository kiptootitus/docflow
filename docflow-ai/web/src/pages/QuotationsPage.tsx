import { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Plus, Search, Trash2, FileText, CheckCircle2, XCircle, Eye,
  Printer, ArrowLeft, Send, BarChart3, Upload, Sparkles,
  TrendingUp, TrendingDown, DollarSign, Users, Activity,
  ChevronRight, X, Download, RefreshCw, FileSpreadsheet,
  Layers, Palette, Check
} from "lucide-react";
import { quotationsApi, companiesApi } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, RadialBarChart, RadialBar
} from "recharts";
import * as XLSX from "xlsx";
import Papa from "papaparse";

// ─────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────
interface ExcelAnalysis {
  summary: {
    totalRows: number;
    totalCols: number;
    sheets: string[];
    numericColumns: string[];
    textColumns: string[];
  };
  stats: Record<string, { min: number; max: number; avg: number; sum: number; count: number }>;
  chartData: {
    bar: { name: string; value: number }[];
    trend: { name: string; value: number }[];
    distribution: { name: string; value: number; color: string }[];
  };
  aiInsights: string;
  rawHeaders: string[];
  sampleRows: any[];
}

// ─────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────
const CHART_COLORS = ["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#84cc16"];

const STATUS_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  draft:    { label: "Draft",    color: "bg-slate-100 text-slate-700 ring-slate-600/10",      icon: FileText    },
  sent:     { label: "Sent",     color: "bg-blue-50 text-blue-700 ring-blue-600/10",          icon: Send        },
  accepted: { label: "Accepted", color: "bg-emerald-50 text-emerald-700 ring-emerald-600/10", icon: CheckCircle2 },
  declined: { label: "Declined", color: "bg-rose-50 text-rose-700 ring-rose-600/10",          icon: XCircle     },
};

const TEMPLATES = [
  { id: "modern",    label: "Modern",    desc: "Clean indigo gradient header" },
  { id: "minimal",   label: "Minimal",   desc: "Typographic, ultra-clean" },
  { id: "executive", label: "Executive", desc: "Navy premium two-column" },
  { id: "bold",      label: "Bold",      desc: "High-contrast full-bleed" },
  { id: "framed",    label: "Blueprint", desc: "Technical mono grid" },
  { id: "darkcard",  label: "Cyber",     desc: "Dark terminal aesthetic" },
];

// ─────────────────────────────────────────────
// SUB COMPONENTS
// ─────────────────────────────────────────────
function ExpiryBadge({ expiryDate }: { expiryDate: string | null }) {
  if (!expiryDate) return <span className="text-gray-400 text-xs">—</span>;
  const days = Math.ceil((new Date(expiryDate).getTime() - Date.now()) / 86400000);
  if (days < 0)   return <span className="inline-flex items-center text-[11px] font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md">Expired</span>;
  if (days === 0) return <span className="inline-flex items-center text-[11px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md">Expires Today</span>;
  return <span className="text-xs text-slate-600 font-semibold">{formatDate(expiryDate)}</span>;
}

// ─────────────────────────────────────────────
// PRINT TEMPLATES
// ─────────────────────────────────────────────
function TemplateModern({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-white min-h-[900px] font-sans text-slate-800 text-xs">
      <div className="bg-gradient-to-br from-indigo-600 to-violet-700 p-10 text-white">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-4">
            {logo ? <img src={logo} alt="logo" className="w-14 h-14 rounded-xl object-cover bg-white/20 p-1" /> : <div className="w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center font-black text-2xl">{(company?.name || "Q")[0]}</div>}
            <div>
              <h2 className="text-xl font-black tracking-tight">{company?.name || "Your Company"}</h2>
              <p className="text-indigo-200 text-[11px] mt-1">{company?.address_line1 || ""}</p>
              <p className="text-indigo-200 text-[11px]">{company?.email || ""}</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-[0.2em] text-indigo-300 font-bold">Quotation</div>
            <div className="text-3xl font-black mt-1">{q.number}</div>
            <div className="text-indigo-200 text-[11px] mt-2">Issued {formatDate(q.issue_date)}</div>
            <div className="text-indigo-200 text-[11px]">Valid until {formatDate(q.expiry_date || q.due_date)}</div>
          </div>
        </div>
      </div>
      <div className="p-10">
        <div className="bg-slate-50 rounded-2xl p-6 mb-8 flex justify-between items-start border border-slate-100">
          <div>
            <div className="text-[9px] uppercase font-black text-slate-400 tracking-widest mb-2">Prepared For</div>
            <div className="text-base font-black text-slate-900">{q.salutation ? `${q.salutation} ` : ""}{q.client_name || "—"}</div>
            {q.client_email && <div className="text-slate-500 text-[11px] mt-1">{q.client_email}</div>}
            {q.client_phone && <div className="text-slate-500 text-[11px]">{q.client_phone}</div>}
          </div>
          <div className="text-right text-[11px] text-slate-500 space-y-1">
            {q.client_address && <div>{q.client_address}</div>}
            {q.client_vat_number && <div>VAT: {q.client_vat_number}</div>}
          </div>
        </div>
        <table className="w-full border-collapse mb-8">
          <thead>
            <tr className="bg-slate-900 text-white text-[9px] uppercase tracking-widest font-black">
              <th className="p-4 text-left rounded-l-lg">Description</th>
              <th className="p-4 text-center w-16">Qty</th>
              <th className="p-4 text-right w-28">Unit Price</th>
              <th className="p-4 text-right w-28 rounded-r-lg">Total</th>
            </tr>
          </thead>
          <tbody>
            {q.line_items?.map((item: any, i: number) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/60"}>
                <td className="p-4 font-semibold text-slate-800">{item.description}</td>
                <td className="p-4 text-center text-slate-500 font-mono">{item.quantity}</td>
                <td className="p-4 text-right text-slate-600 font-mono">{fmt(item.unit_price)}</td>
                <td className="p-4 text-right font-black text-indigo-700 font-mono">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex justify-end mb-8">
          <div className="w-72 bg-gradient-to-br from-indigo-600 to-violet-700 rounded-2xl p-6 text-white">
            <div className="text-[10px] uppercase tracking-widest font-black text-indigo-200 mb-2">Total Amount</div>
            <div className="text-3xl font-black">{fmt(q.total_amount)}</div>
            <div className="text-indigo-200 text-[11px] mt-2">{q.currency}</div>
          </div>
        </div>
        {q.notes && <div className="bg-amber-50 border border-amber-100 rounded-xl p-4 text-slate-600 text-[11px] leading-relaxed"><strong className="text-amber-800">Notes:</strong> {q.notes}</div>}
      </div>
    </div>
  );
}

function TemplateMinimal({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-white min-h-[900px] font-serif text-slate-900 text-xs p-14">
      <div className="flex justify-between items-start pb-8 border-b border-slate-900 mb-10">
        <div className="flex items-center gap-4">
          {logo ? <img src={logo} alt="logo" className="w-10 h-10 object-contain" /> : null}
          <div>
            <h2 className="text-lg font-bold tracking-tight">{company?.name || "Your Company"}</h2>
            <p className="text-slate-400 text-[10px] mt-0.5">{company?.address_line1}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[28px] font-bold tracking-tighter text-slate-200 -mb-2">QUOTATION</div>
          <div className="text-sm font-bold text-slate-900">{q.number}</div>
          <div className="text-slate-400 text-[10px] mt-1">{formatDate(q.issue_date)}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-12 mb-10">
        <div>
          <div className="text-[9px] uppercase tracking-[0.2em] text-slate-400 font-bold mb-3">Bill To</div>
          <div className="text-base font-bold">{q.salutation ? `${q.salutation} ` : ""}{q.client_name}</div>
          {q.client_email && <div className="text-slate-500 text-[11px] mt-1">{q.client_email}</div>}
          {q.client_phone && <div className="text-slate-500 text-[11px]">{q.client_phone}</div>}
          {q.client_address && <div className="text-slate-500 text-[11px]">{q.client_address}</div>}
        </div>
        <div className="text-right">
          <div className="text-[9px] uppercase tracking-[0.2em] text-slate-400 font-bold mb-3">Valid Until</div>
          <div className="text-base font-bold">{formatDate(q.expiry_date || q.due_date)}</div>
        </div>
      </div>
      <table className="w-full mb-10">
        <thead>
          <tr className="border-b-2 border-slate-900 text-[9px] uppercase tracking-widest font-bold text-slate-400">
            <th className="py-3 text-left">Item</th>
            <th className="py-3 text-center">Qty</th>
            <th className="py-3 text-right">Rate</th>
            <th className="py-3 text-right">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {q.line_items?.map((item: any, i: number) => (
            <tr key={i}>
              <td className="py-4 font-medium">{item.description}</td>
              <td className="py-4 text-center text-slate-400 font-mono">{item.quantity}</td>
              <td className="py-4 text-right text-slate-500 font-mono">{fmt(item.unit_price)}</td>
              <td className="py-4 text-right font-bold font-mono">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-slate-900">
            <td colSpan={3} className="pt-4 text-right text-[9px] uppercase tracking-widest font-black text-slate-400">Total</td>
            <td className="pt-4 text-right text-xl font-black">{fmt(q.total_amount)}</td>
          </tr>
        </tfoot>
      </table>
      {q.notes && <div className="text-slate-400 text-[11px] italic border-t border-slate-100 pt-6">{q.notes}</div>}
    </div>
  );
}

function TemplateExecutive({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-white min-h-[900px] font-sans text-xs flex">
      <div className="w-56 bg-slate-900 text-white p-8 flex-shrink-0 flex flex-col">
        <div className="mb-8">
          {logo ? <img src={logo} alt="logo" className="w-12 h-12 rounded-lg object-cover mb-4" /> : <div className="w-12 h-12 bg-white/10 rounded-lg mb-4 flex items-center justify-center font-black text-xl">{(company?.name || "Q")[0]}</div>}
          <h2 className="text-sm font-black leading-tight">{company?.name || "Your Company"}</h2>
          <p className="text-slate-400 text-[10px] mt-2">{company?.address_line1}</p>
          <p className="text-slate-400 text-[10px]">{company?.email}</p>
        </div>
        <div className="border-t border-white/10 pt-6 space-y-4">
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Quotation</div>
            <div className="text-sm font-black mt-1">{q.number}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Issued</div>
            <div className="text-[11px] mt-1">{formatDate(q.issue_date)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Valid Until</div>
            <div className="text-[11px] mt-1">{formatDate(q.expiry_date || q.due_date)}</div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Currency</div>
            <div className="text-[11px] mt-1">{q.currency}</div>
          </div>
        </div>
        <div className="mt-auto border-t border-white/10 pt-6">
          <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-2">Total Value</div>
          <div className="text-2xl font-black text-white">{fmt(q.total_amount)}</div>
        </div>
      </div>
      <div className="flex-1 p-10">
        <div className="mb-10">
          <div className="text-[9px] uppercase tracking-widest text-slate-400 font-bold mb-3">Prepared For</div>
          <div className="text-xl font-black text-slate-900">{q.salutation ? `${q.salutation} ` : ""}{q.client_name}</div>
          {q.client_email && <div className="text-slate-500 text-[11px] mt-1">{q.client_email}</div>}
          {q.client_phone && <div className="text-slate-500 text-[11px]">{q.client_phone}</div>}
          {q.client_address && <div className="text-slate-500 text-[11px]">{q.client_address}</div>}
        </div>
        <table className="w-full mb-8">
          <thead>
            <tr className="bg-slate-50 text-[9px] uppercase tracking-widest font-black text-slate-400">
              <th className="p-3 text-left">Description</th>
              <th className="p-3 text-center w-14">Qty</th>
              <th className="p-3 text-right w-24">Unit</th>
              <th className="p-3 text-right w-28">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {q.line_items?.map((item: any, i: number) => (
              <tr key={i} className="hover:bg-slate-50/50">
                <td className="p-3 font-semibold text-slate-800">{item.description}</td>
                <td className="p-3 text-center text-slate-400 font-mono">{item.quantity}</td>
                <td className="p-3 text-right text-slate-500 font-mono">{fmt(item.unit_price)}</td>
                <td className="p-3 text-right font-black text-slate-900 font-mono">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {q.notes && <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-slate-500 text-[11px] leading-relaxed"><strong>Notes:</strong> {q.notes}</div>}
      </div>
    </div>
  );
}

function TemplateBold({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-white min-h-[900px] font-sans text-xs">
      <div className="bg-amber-400 p-10">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-4">
            {logo ? <img src={logo} alt="logo" className="w-14 h-14 rounded object-cover border-2 border-black" /> : <div className="w-14 h-14 bg-black flex items-center justify-center font-black text-amber-400 text-2xl">{(company?.name || "Q")[0]}</div>}
            <div>
              <h2 className="text-xl font-black text-black uppercase tracking-tighter">{company?.name || "Your Company"}</h2>
              <p className="text-black/60 text-[11px] mt-1">{company?.address_line1}</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-5xl font-black text-black/10 tracking-tighter leading-none">QUO</div>
            <div className="text-lg font-black text-black -mt-2">{q.number}</div>
            <div className="text-black/70 text-[11px] mt-1">{formatDate(q.issue_date)}</div>
          </div>
        </div>
      </div>
      <div className="p-10">
        <div className="border-4 border-black p-6 mb-8 flex justify-between items-start">
          <div>
            <div className="text-[9px] uppercase font-black tracking-widest text-black/40 mb-1">For</div>
            <div className="text-lg font-black">{q.salutation ? `${q.salutation} ` : ""}{q.client_name}</div>
            {q.client_email && <div className="text-black/60 text-[11px]">{q.client_email}</div>}
            {q.client_phone && <div className="text-black/60 text-[11px]">{q.client_phone}</div>}
          </div>
          <div className="text-right">
            <div className="text-[9px] uppercase font-black tracking-widest text-black/40 mb-1">Valid Until</div>
            <div className="font-black text-base">{formatDate(q.expiry_date || q.due_date)}</div>
          </div>
        </div>
        <table className="w-full border-collapse mb-8">
          <thead>
            <tr className="bg-black text-white text-[9px] uppercase tracking-widest font-black">
              <th className="p-4 text-left">Item</th>
              <th className="p-4 text-center w-14">Qty</th>
              <th className="p-4 text-right w-28">Rate</th>
              <th className="p-4 text-right w-28">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y-2 divide-black/5">
            {q.line_items?.map((item: any, i: number) => (
              <tr key={i} className={i % 2 === 0 ? "" : "bg-amber-50"}>
                <td className="p-4 font-bold">{item.description}</td>
                <td className="p-4 text-center font-mono">{item.quantity}</td>
                <td className="p-4 text-right font-mono text-black/60">{fmt(item.unit_price)}</td>
                <td className="p-4 text-right font-black font-mono">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="flex justify-end">
          <div className="bg-black text-white p-6 w-64">
            <div className="text-[9px] uppercase tracking-widest font-black text-white/40 mb-1">Total</div>
            <div className="text-3xl font-black text-amber-400">{fmt(q.total_amount)}</div>
          </div>
        </div>
        {q.notes && <div className="mt-8 border-l-4 border-amber-400 pl-4 text-black/60 text-[11px] italic">{q.notes}</div>}
      </div>
    </div>
  );
}

function TemplateBlueprint({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-white min-h-[900px] font-mono text-slate-900 text-xs border-4 border-slate-900 p-8">
      <div className="border-b-2 border-slate-900 pb-6 mb-8 flex justify-between items-end">
        <div className="flex items-center gap-3">
          {logo ? <img src={logo} alt="logo" className="w-10 h-10 border-2 border-slate-900 object-cover" /> : <div className="w-10 h-10 bg-slate-900 text-white font-black flex items-center justify-center">{(company?.name || "Q")[0]}</div>}
          <div>
            <div className="text-[10px] font-black uppercase tracking-widest">[BLUEPRINT ESTIMATE]</div>
            <h2 className="font-black text-sm uppercase">{company?.name || "Your Company"}</h2>
          </div>
        </div>
        <div className="text-right">
          <div className="font-black text-sm bg-slate-900 text-white px-3 py-1">{q.number}</div>
          <div className="text-slate-500 text-[10px] mt-1">ISSUED: {formatDate(q.issue_date)}</div>
          <div className="text-slate-500 text-[10px]">VALID_TO: {formatDate(q.expiry_date || q.due_date)}</div>
        </div>
      </div>
      <div className="border border-slate-300 bg-slate-50/50 p-4 grid grid-cols-2 gap-4 mb-8">
        <div>
          <span className="text-[9px] text-slate-400 font-black uppercase block tracking-wider">TAG_CLIENT:</span>
          <span className="font-black">{q.salutation ? `${q.salutation} ` : ""}{q.client_name}</span>
          {q.client_email && <span className="block text-slate-500 text-[10px]">{q.client_email}</span>}
          {q.client_phone && <span className="block text-slate-500 text-[10px]">{q.client_phone}</span>}
          {q.client_address && <span className="block text-slate-500 text-[10px]">{q.client_address}</span>}
        </div>
        <div className="text-right">
          <span className="text-[9px] text-slate-400 font-black uppercase block tracking-wider">CURRENCY_CODE:</span>
          <span className="font-black">{q.currency}</span>
        </div>
      </div>
      <div className="border border-slate-900 rounded-sm overflow-hidden mb-8">
        <div className="bg-slate-900 text-white text-[9px] uppercase font-black grid grid-cols-12 p-2.5 tracking-widest">
          <span className="col-span-6">ITEM_SPECIFICATION</span>
          <span className="col-span-2 text-center">METRIC</span>
          <span className="col-span-2 text-right">UNIT_RATE</span>
          <span className="col-span-2 text-right">VAL_TOTAL</span>
        </div>
        {q.line_items?.map((item: any, i: number) => (
          <div key={i} className="grid grid-cols-12 p-2.5 border-b border-slate-200 bg-white items-center last:border-0">
            <span className="col-span-6 font-bold truncate">{item.description}</span>
            <span className="col-span-2 text-center text-slate-500">{item.quantity}</span>
            <span className="col-span-2 text-right text-slate-500">{fmt(item.unit_price)}</span>
            <span className="col-span-2 text-right font-black">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</span>
          </div>
        ))}
      </div>
      <div className="flex justify-between items-center border-2 border-slate-900 p-4 bg-slate-100/50">
        <span className="font-black uppercase tracking-wider text-sm">SUM_TOTAL_VALUATION:</span>
        <span className="text-xl font-black bg-slate-900 text-white px-4 py-2">{fmt(q.total_amount)}</span>
      </div>
      {q.notes && <div className="mt-6 text-slate-500 text-[10px] border border-slate-200 p-3"><span className="font-black text-slate-700">NOTES: </span>{q.notes}</div>}
    </div>
  );
}

function TemplateCyber({ q, company, logo }: { q: any; company: any; logo: string | null }) {
  const fmt = (v: any) => formatCurrency(parseFloat(String(v || 0)), q.currency);
  return (
    <div className="bg-slate-950 min-h-[900px] font-mono text-emerald-400 text-xs p-8 rounded-2xl">
      <div className="border-b border-slate-800 pb-6 mb-8 flex justify-between items-start">
        <div className="flex items-center gap-3">
          {logo ? <img src={logo} alt="logo" className="w-12 h-12 border border-emerald-500/30 rounded object-cover" /> : <div className="w-12 h-12 border border-emerald-500/20 bg-emerald-500/10 flex items-center justify-center font-black text-white text-xl">{(company?.name || "Q")[0]}</div>}
          <div>
            <div className="text-[10px] text-slate-500 font-bold">// CORPORATE_INSTANCE</div>
            <h2 className="text-sm font-bold text-white">{company?.name || "Your Company"}</h2>
            <div className="text-slate-500 text-[10px]">{company?.email}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-slate-500">DOCUMENT_TYPE: QUOTATION</div>
          <div className="text-lg font-bold text-white mt-1">{q.number}</div>
          <div className="text-slate-500 text-[10px] mt-1">TIMESTAMP: {formatDate(q.issue_date)}</div>
          <div className="text-slate-500 text-[10px]">TTL: {formatDate(q.expiry_date || q.due_date)}</div>
        </div>
      </div>
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 mb-8 space-y-1.5">
        <div className="text-[9px] text-slate-500 font-bold uppercase tracking-widest mb-3"># CLIENT_PARAMETERS</div>
        <div><span className="text-emerald-500">target_name</span> = <span className="text-amber-300">"{q.salutation ? `${q.salutation} ` : ""}{q.client_name}"</span></div>
        {q.client_email && <div><span className="text-slate-500">email</span> = <span className="text-slate-300">"{q.client_email}"</span></div>}
        {q.client_phone && <div><span className="text-slate-500">phone</span> = <span className="text-slate-300">"{q.client_phone}"</span></div>}
        {q.client_address && <div><span className="text-slate-500">address</span> = <span className="text-slate-300">"{q.client_address}"</span></div>}
        <div><span className="text-slate-500">currency</span> = <span className="text-slate-300">"{q.currency}"</span></div>
      </div>
      <div className="space-y-2 mb-8">
        <div className="text-[9px] text-slate-500 font-bold uppercase tracking-widest mb-3"># SCOPE_ITEMS[]</div>
        {q.line_items?.map((item: any, i: number) => (
          <div key={i} className="bg-slate-900/40 border border-slate-900 rounded-lg p-4 flex justify-between items-center">
            <div>
              <div className="text-white font-bold">{item.description}</div>
              <div className="text-slate-500 text-[10px] mt-0.5">qty: {item.quantity} | rate: {fmt(item.unit_price)}</div>
            </div>
            <div className="text-emerald-300 font-bold text-sm">{fmt(parseFloat(item.amount || String(item.quantity * item.unit_price)))}</div>
          </div>
        ))}
      </div>
      <div className="border-t border-slate-800 pt-6 flex justify-between items-center">
        <span className="text-slate-500 font-bold uppercase tracking-widest text-[10px]">NET_AGGREGATE_VALUE</span>
        <span className="text-2xl font-black text-white">{fmt(q.total_amount)}</span>
      </div>
      {q.notes && <div className="mt-6 text-slate-500 text-[10px] bg-slate-900/40 p-3 rounded-lg border border-slate-800"><span className="text-emerald-500">// notes: </span>{q.notes}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────
// EXCEL ANALYSIS ENGINE
// ─────────────────────────────────────────────
function analyzeExcelFile(file: File): Promise<ExcelAnalysis> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: "array" });
        const sheetName = workbook.SheetNames[0];
        const worksheet = workbook.Sheets[sheetName];
        const json: any[] = XLSX.utils.sheet_to_json(worksheet, { defval: "" });

        if (!json.length) { reject(new Error("Empty sheet")); return; }

        const headers = Object.keys(json[0]);
        const numericCols: string[] = [];
        const textCols: string[] = [];

        headers.forEach(h => {
          const vals = json.map(r => r[h]).filter(v => v !== "" && v !== null);
          const nums = vals.map(v => parseFloat(String(v))).filter(v => !isNaN(v));
          if (nums.length / vals.length > 0.6) numericCols.push(h);
          else textCols.push(h);
        });

        const stats: ExcelAnalysis["stats"] = {};
        numericCols.forEach(col => {
          const vals = json.map(r => parseFloat(String(r[col]))).filter(v => !isNaN(v));
          stats[col] = {
            min: Math.min(...vals),
            max: Math.max(...vals),
            avg: vals.reduce((a, b) => a + b, 0) / vals.length,
            sum: vals.reduce((a, b) => a + b, 0),
            count: vals.length,
          };
        });

        const primaryNumCol = numericCols[0];
        const primaryTextCol = textCols[0];

        const bar = primaryNumCol && primaryTextCol
          ? json.slice(0, 12).map(r => ({ name: String(r[primaryTextCol]).slice(0, 18), value: parseFloat(String(r[primaryNumCol])) || 0 }))
          : numericCols.slice(0, 8).map(col => ({ name: col.slice(0, 18), value: stats[col]?.sum || 0 }));

        const trend = json.slice(0, 20).map((r, i) => ({
          name: primaryTextCol ? String(r[primaryTextCol]).slice(0, 10) : `Row ${i + 1}`,
          value: primaryNumCol ? parseFloat(String(r[primaryNumCol])) || 0 : 0,
        }));

        const distribution = numericCols.slice(0, 6).map((col, i) => ({
          name: col.slice(0, 16),
          value: Math.round((stats[col]?.sum || 0) * 100) / 100,
          color: CHART_COLORS[i % CHART_COLORS.length],
        }));

        const topInsight = primaryNumCol && stats[primaryNumCol]
          ? `${primaryNumCol} ranges from ${stats[primaryNumCol].min.toLocaleString()} to ${stats[primaryNumCol].max.toLocaleString()} with an average of ${stats[primaryNumCol].avg.toFixed(2)}.`
          : "";

        resolve({
          summary: {
            totalRows: json.length,
            totalCols: headers.length,
            sheets: workbook.SheetNames,
            numericColumns: numericCols,
            textColumns: textCols,
          },
          stats,
          chartData: { bar, trend, distribution },
          aiInsights: topInsight,
          rawHeaders: headers,
          sampleRows: json.slice(0, 5),
        });
      } catch (err) {
        reject(err);
      }
    };
    reader.readAsArrayBuffer(file);
  });
}

// ─────────────────────────────────────────────
// AI ANALYSIS COMPONENT
// ─────────────────────────────────────────────
function ExcelAnalysisPanel({ onClose }: { onClose: () => void }) {
  const [analysis, setAnalysis] = useState<ExcelAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiReport, setAiReport] = useState<string>("");
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const processFile = async (file: File) => {
    setLoading(true);
    setFileName(file.name);
    try {
      const result = await analyzeExcelFile(file);
      setAnalysis(result);
      // Trigger AI insights
      setAiLoading(true);
      const summaryText = `
Dataset: ${file.name}
Rows: ${result.summary.totalRows}, Columns: ${result.summary.totalCols}
Numeric columns: ${result.summary.numericColumns.join(", ")}
Text columns: ${result.summary.textColumns.join(", ")}
Stats: ${JSON.stringify(result.stats, null, 2)}
Sample (first 3 rows): ${JSON.stringify(result.sampleRows.slice(0, 3))}
      `.trim();

      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 1000,
          messages: [{
            role: "user",
            content: `You are a world-class financial data analyst. Analyze this dataset and provide a concise executive-level report with: 1) Key findings (3-5 bullet points), 2) Trends and anomalies, 3) Actionable business recommendations, 4) Risk flags if any. Be specific with numbers. Dataset: ${summaryText}`
          }]
        })
      });
      const data = await res.json();
      const text = data.content?.map((b: any) => b.text || "").join("") || "";
      setAiReport(text);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      setAiLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload?.length) {
      return (
        <div className="bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-xs text-white shadow-2xl">
          <p className="font-bold text-slate-300 mb-1">{label}</p>
          {payload.map((p: any, i: number) => (
            <p key={i} style={{ color: p.color }}>{p.name}: <span className="font-black">{typeof p.value === "number" ? p.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : p.value}</span></p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center overflow-y-auto py-8 px-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-6xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-violet-600 to-indigo-600 rounded-xl flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-black text-slate-900">Excel Intelligence Analysis</h2>
              <p className="text-xs text-slate-400">{fileName || "Upload a spreadsheet for AI-powered insights"}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-xl transition-colors"><X className="w-5 h-5 text-slate-500" /></button>
        </div>

        <div className="p-6">
          {/* Upload zone */}
          {!analysis && (
            <div
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              onClick={() => fileRef.current?.click()}
              className={cn(
                "border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition-all",
                dragging ? "border-indigo-500 bg-indigo-50" : "border-gray-200 hover:border-indigo-300 hover:bg-gray-50"
              )}
            >
              {loading ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                  <p className="text-sm font-bold text-indigo-600">Analyzing spreadsheet...</p>
                </div>
              ) : (
                <>
                  <FileSpreadsheet className="w-14 h-14 text-gray-300 mx-auto mb-4" />
                  <p className="text-base font-black text-slate-700">Drop your Excel or CSV file here</p>
                  <p className="text-sm text-slate-400 mt-1">or click to browse — .xlsx, .xls, .csv supported</p>
                </>
              )}
              <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) processFile(f); }} />
            </div>
          )}

          {analysis && (
            <div className="space-y-6">
              {/* Summary cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {[
                  { label: "Total Rows", value: analysis.summary.totalRows.toLocaleString(), icon: Layers, color: "from-indigo-500 to-violet-600" },
                  { label: "Columns", value: analysis.summary.totalCols, icon: Activity, color: "from-cyan-500 to-blue-600" },
                  { label: "Numeric Fields", value: analysis.summary.numericColumns.length, icon: TrendingUp, color: "from-emerald-500 to-teal-600" },
                  { label: "Data Sheets", value: analysis.summary.sheets.length, icon: FileSpreadsheet, color: "from-amber-500 to-orange-600" },
                ].map((c, i) => (
                  <div key={i} className={`bg-gradient-to-br ${c.color} rounded-2xl p-5 text-white`}>
                    <c.icon className="w-5 h-5 mb-2 opacity-80" />
                    <div className="text-2xl font-black">{c.value}</div>
                    <div className="text-[10px] font-bold uppercase tracking-wider opacity-80 mt-1">{c.label}</div>
                  </div>
                ))}
              </div>

              {/* Charts row */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Bar chart */}
                <div className="bg-slate-50 rounded-2xl p-5 border border-slate-100">
                  <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-indigo-600" /> Value Distribution</h3>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={analysis.chartData.bar} margin={{ top: 5, right: 5, left: 0, bottom: 30 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8", fontWeight: 700 }} angle={-30} textAnchor="end" interval={0} />
                      <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
                      <Tooltip content={<CustomTooltip />} />
                      <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]}>
                        {analysis.chartData.bar.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Trend line */}
                <div className="bg-slate-50 rounded-2xl p-5 border border-slate-100">
                  <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-emerald-600" /> Data Trend</h3>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={analysis.chartData.trend} margin={{ top: 5, right: 5, left: 0, bottom: 30 }}>
                      <defs>
                        <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                      <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8", fontWeight: 700 }} angle={-30} textAnchor="end" interval={0} />
                      <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} />
                      <Tooltip content={<CustomTooltip />} />
                      <Area type="monotone" dataKey="value" stroke="#6366f1" strokeWidth={2.5} fill="url(#trendGrad)" dot={{ fill: "#6366f1", r: 3 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Pie + stats row */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Pie */}
                <div className="bg-slate-50 rounded-2xl p-5 border border-slate-100">
                  <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2"><Activity className="w-4 h-4 text-violet-600" /> Column Share</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={analysis.chartData.distribution} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false} fontSize={8}>
                        {analysis.chartData.distribution.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                      </Pie>
                      <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                {/* Stats table */}
                <div className="lg:col-span-2 bg-slate-50 rounded-2xl p-5 border border-slate-100">
                  <h3 className="text-sm font-black text-slate-800 mb-4 flex items-center gap-2"><DollarSign className="w-4 h-4 text-amber-600" /> Column Statistics</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-[9px] uppercase font-black text-slate-400 tracking-wider border-b border-slate-200">
                          <th className="text-left pb-2">Column</th>
                          <th className="text-right pb-2">Min</th>
                          <th className="text-right pb-2">Max</th>
                          <th className="text-right pb-2">Avg</th>
                          <th className="text-right pb-2">Sum</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {Object.entries(analysis.stats).map(([col, s]) => (
                          <tr key={col} className="hover:bg-white transition-colors">
                            <td className="py-2 font-bold text-slate-700 truncate max-w-[120px]">{col}</td>
                            <td className="py-2 text-right font-mono text-slate-500">{s.min.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                            <td className="py-2 text-right font-mono text-slate-500">{s.max.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                            <td className="py-2 text-right font-mono text-indigo-600 font-bold">{s.avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                            <td className="py-2 text-right font-mono font-black text-slate-900">{s.sum.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* AI Insights */}
              <div className="bg-gradient-to-br from-indigo-950 to-slate-950 rounded-2xl p-6 text-white">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-8 h-8 bg-indigo-500/20 rounded-lg flex items-center justify-center"><Sparkles className="w-4 h-4 text-indigo-300" /></div>
                  <h3 className="text-sm font-black">AI Executive Report</h3>
                  {aiLoading && <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin ml-auto" />}
                </div>
                {aiLoading && !aiReport && (
                  <div className="space-y-2">
                    {[100, 80, 90, 70, 85].map((w, i) => <div key={i} className="h-3 bg-white/5 rounded-full animate-pulse" style={{ width: `${w}%` }} />)}
                  </div>
                )}
                {aiReport && (
                  <div className="text-slate-300 text-xs leading-relaxed whitespace-pre-wrap">{aiReport}</div>
                )}
              </div>

              {/* Reset */}
              <div className="flex justify-end">
                <button onClick={() => { setAnalysis(null); setAiReport(""); setFileName(""); }} className="flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-slate-700 transition-colors">
                  <RefreshCw className="w-3.5 h-3.5" /> Analyze another file
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// TEMPLATE PICKER MODAL
// ─────────────────────────────────────────────
function TemplatePicker({ current, logo, onLogoChange, onSelect, onClose, q, company }: {
  current: string;
  logo: string | null;
  onLogoChange: (url: string) => void;
  onSelect: (id: string) => void;
  onClose: () => void;
  q: any;
  company: any;
}) {
  const fileRef = useRef<HTMLInputElement>(null);

  const renderMini = (id: string) => {
    const props = { q, company, logo };
    const map: Record<string, React.ReactNode> = {
      modern:    <TemplateModern    {...props} />,
      minimal:   <TemplateMinimal   {...props} />,
      executive: <TemplateExecutive {...props} />,
      bold:      <TemplateBold      {...props} />,
      framed:    <TemplateBlueprint {...props} />,
      darkcard:  <TemplateCyber     {...props} />,
    };
    return map[id] || null;
  };

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl flex items-center justify-center"><Palette className="w-4 h-4 text-white" /></div>
            <h2 className="text-base font-black text-slate-900">Choose Quotation Template</h2>
          </div>
          <div className="flex items-center gap-3">
            {/* Logo upload in picker */}
            <button onClick={() => fileRef.current?.click()} className="flex items-center gap-2 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-2 rounded-xl transition-colors">
              <Upload className="w-3.5 h-3.5" /> {logo ? "Change Logo" : "Upload Logo"}
            </button>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => {
              const f = e.target.files?.[0];
              if (f) onLogoChange(URL.createObjectURL(f));
            }} />
            <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-xl transition-colors"><X className="w-4 h-4 text-slate-500" /></button>
          </div>
        </div>
        <div className="overflow-y-auto p-6 grid grid-cols-2 lg:grid-cols-3 gap-5">
          {TEMPLATES.map(t => (
            <div key={t.id} onClick={() => onSelect(t.id)} className={cn("relative cursor-pointer rounded-2xl overflow-hidden border-2 transition-all hover:shadow-xl group", current === t.id ? "border-indigo-500 shadow-lg shadow-indigo-100" : "border-gray-100 hover:border-indigo-200")}>
              {/* Mini preview */}
              <div className="h-52 overflow-hidden pointer-events-none">
                <div className="scale-[0.35] origin-top-left w-[285%]">
                  {renderMini(t.id)}
                </div>
              </div>
              <div className="p-3 bg-white border-t border-gray-100 flex items-center justify-between">
                <div>
                  <div className="text-xs font-black text-slate-900">{t.label}</div>
                  <div className="text-[10px] text-slate-400">{t.desc}</div>
                </div>
                {current === t.id && <div className="w-5 h-5 bg-indigo-600 rounded-full flex items-center justify-center flex-shrink-0"><Check className="w-3 h-3 text-white" /></div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// PRINT / DOCUMENT VIEW
// ─────────────────────────────────────────────
function DocumentView({ q, company, logo, template, onBack }: { q: any; company: any; logo: string | null; template: string; onBack: () => void }) {
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [activeTemplate, setActiveTemplate] = useState(template);
  const [currentLogo, setCurrentLogo] = useState(logo);

  const props = { q, company, logo: currentLogo };
  const templateMap: Record<string, React.ReactNode> = {
    modern:    <TemplateModern    {...props} />,
    minimal:   <TemplateMinimal   {...props} />,
    executive: <TemplateExecutive {...props} />,
    bold:      <TemplateBold      {...props} />,
    framed:    <TemplateBlueprint {...props} />,
    darkcard:  <TemplateCyber     {...props} />,
  };

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto min-h-screen bg-gray-50 animate-fade-in print:p-0 print:bg-white">
      {/* Controls */}
      <div className="flex items-center justify-between border-b border-gray-200 pb-4 mb-6 print:hidden bg-white rounded-2xl p-4 shadow-sm">
        <button onClick={onBack} className="flex items-center gap-2 text-sm text-gray-500 hover:text-slate-900 font-bold transition-colors">
          <ArrowLeft className="w-4 h-4" /> Back to Pipeline
        </button>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowTemplatePicker(true)} className="flex items-center gap-2 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-xl transition-colors">
            <Palette className="w-3.5 h-3.5" /> Change Template
          </button>
          <button onClick={() => window.print()} className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-sm">
            <Printer className="w-4 h-4" /> Print / Export PDF
          </button>
        </div>
      </div>

      {/* Document */}
      <div className="shadow-2xl rounded-2xl overflow-hidden print:shadow-none print:rounded-none">
        {templateMap[activeTemplate] || templateMap.modern}
      </div>

      {showTemplatePicker && (
        <TemplatePicker
          current={activeTemplate}
          logo={currentLogo}
          onLogoChange={setCurrentLogo}
          onSelect={id => { setActiveTemplate(id); setShowTemplatePicker(false); }}
          onClose={() => setShowTemplatePicker(false)}
          q={q}
          company={company}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────
export default function QuotationsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [documentViewTarget, setDocumentViewTarget] = useState<any | null>(null);
  const [activeTemplate, setActiveTemplate] = useState("modern");
  const [uploadedLogo, setUploadedLogo] = useState<string | null>(null);
  const [showExcelAnalysis, setShowExcelAnalysis] = useState(false);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const logoFileRef = useRef<HTMLInputElement>(null);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data, isLoading } = useQuery({
    queryKey: ["quotations", search, statusFilter],
    queryFn: () => quotationsApi.list({ ...(search && { search }), ...(statusFilter && { status: statusFilter }) }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => quotationsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quotations"] }),
  });

  const quotations = data?.data?.results ?? [];
  const stats = {
    total: data?.data?.count ?? 0,
    accepted: quotations.filter(q => q.status === "accepted").length,
    pending: quotations.filter(q => q.status === "sent").length,
    totalValue: quotations.reduce((s, q) => s + parseFloat(q.total_amount ?? "0"), 0),
  };

  const logo = uploadedLogo || company?.logo_url || null;

  if (documentViewTarget) {
    return (
      <DocumentView
        q={documentViewTarget}
        company={company}
        logo={logo}
        template={activeTemplate}
        onBack={() => setDocumentViewTarget(null)}
      />
    );
  }

  return (
    <div className="p-4 sm:p-8 bg-gray-50/30 min-h-screen print:hidden">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Quotations Pipeline</h1>
          <p className="text-gray-400 text-xs mt-0.5">{stats.total} total proposals</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Logo upload shortcut */}
          <button
            onClick={() => logoFileRef.current?.click()}
            className="flex items-center gap-2 text-xs font-bold text-slate-600 bg-white border border-gray-200 hover:border-indigo-300 hover:text-indigo-600 px-3 py-2 rounded-xl transition-all shadow-xs"
          >
            <Upload className="w-3.5 h-3.5" />
            {uploadedLogo ? "Logo Uploaded ✓" : "Upload Logo"}
          </button>
          <input ref={logoFileRef} type="file" accept="image/*" className="hidden" onChange={e => {
            const f = e.target.files?.[0];
            if (f) setUploadedLogo(URL.createObjectURL(f));
          }} />

          {/* Template picker */}
          <button
            onClick={() => setShowTemplatePicker(true)}
            className="flex items-center gap-2 text-xs font-bold text-slate-600 bg-white border border-gray-200 hover:border-indigo-300 hover:text-indigo-600 px-3 py-2 rounded-xl transition-all shadow-xs"
          >
            <Palette className="w-3.5 h-3.5" /> Templates
          </button>

          {/* Excel analysis */}
          <button
            onClick={() => setShowExcelAnalysis(true)}
            className="flex items-center gap-2 text-xs font-bold text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 px-3 py-2 rounded-xl transition-all"
          >
            <BarChart3 className="w-3.5 h-3.5" /> Analyze Excel
          </button>

          <Link
            to="/quotations/new"
            className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-sm transition-all"
          >
            <Plus className="w-4 h-4" /> New Proposal
          </Link>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Quotes",    value: stats.total,                                                    color: "bg-white text-slate-900 border-gray-100" },
          { label: "Awaiting Reply",  value: stats.pending,                                                  color: "bg-white text-blue-600 border-gray-100" },
          { label: "Accepted Deals",  value: stats.accepted,                                                 color: "bg-white text-emerald-600 border-gray-100" },
          { label: "Pipeline Worth",  value: formatCurrency(stats.totalValue, company?.default_currency ?? "KES"), color: "bg-slate-900 text-white border-transparent shadow-md" },
        ].map((s, idx) => (
          <div key={idx} className={cn("rounded-2xl p-5 border transition-all hover:scale-[1.01]", s.color)}>
            <p className="text-[10px] sm:text-xs font-bold uppercase tracking-wider opacity-70 truncate">{s.label}</p>
            <p className="text-xl sm:text-2xl font-black mt-1.5 truncate tracking-tight">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
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

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] table-auto border-collapse text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-slate-50/60 text-gray-400 font-bold text-[11px] uppercase tracking-wider">
                <th className="px-6 py-4">Reference</th>
                <th className="px-6 py-4">Client</th>
                <th className="px-6 py-4 text-right">Value</th>
                <th className="px-6 py-4 text-center">Status</th>
                <th className="px-6 py-4">Expires</th>
                <th className="px-6 py-4 w-12"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 font-medium text-slate-700">
              {isLoading && (
                <tr><td colSpan={6} className="px-6 py-12 text-center text-gray-400 animate-pulse">Loading pipeline...</td></tr>
              )}
              {!isLoading && quotations.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-16 text-center text-gray-400 text-sm">No proposals found.</td></tr>
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
                      <p className="text-[10px] text-gray-400 mt-0.5">{formatDate(q.issue_date)}</p>
                    </td>
                    <td className="px-6 py-4 text-slate-900 font-bold">
                      {q.salutation ? `${q.salutation} ` : ""}{q.client_name || "—"}
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
                      <button type="button" onClick={() => { if (confirm("Delete this proposal?")) deleteMutation.mutate(q.id); }} className="p-1.5 text-gray-400 hover:text-rose-500 rounded-lg hover:bg-rose-50 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity">
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

      {/* Modals */}
      {showExcelAnalysis && <ExcelAnalysisPanel onClose={() => setShowExcelAnalysis(false)} />}

      {showTemplatePicker && (
        <TemplatePicker
          current={activeTemplate}
          logo={logo}
          onLogoChange={setUploadedLogo}
          onSelect={id => { setActiveTemplate(id); setShowTemplatePicker(false); }}
          onClose={() => setShowTemplatePicker(false)}
          q={quotations[0] || { number: "QUO-001", client_name: "Sample Client", line_items: [{ description: "Service Item", quantity: 1, unit_price: 5000, amount: "5000" }], total_amount: "5000", currency: "KES", issue_date: new Date().toISOString(), expiry_date: null, due_date: new Date(Date.now() + 30 * 86400000).toISOString() }}
          company={company}
        />
      )}
    </div>
  );
}