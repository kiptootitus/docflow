import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Plus, Search, Trash2, FileText, CheckCircle2, XCircle, Eye, Printer, ArrowLeft, Send, BarChart3, Upload, Sparkles, TrendingUp, DollarSign, Activity, X, RefreshCw, FileSpreadsheet, Layers, Palette, Check } from "lucide-react";
import { quotationsApi, companiesApi } from "@/lib/api";
import { formatCurrency, formatDate, cn } from "@/lib/utils";
import { AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import * as XLSX from "xlsx";
// ─────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────
const CHART_COLORS = ["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#84cc16"];
const STATUS_META = {
    draft: { label: "Draft", color: "bg-slate-100 text-slate-700 ring-slate-600/10", icon: FileText },
    sent: { label: "Sent", color: "bg-blue-50 text-blue-700 ring-blue-600/10", icon: Send },
    accepted: { label: "Accepted", color: "bg-emerald-50 text-emerald-700 ring-emerald-600/10", icon: CheckCircle2 },
    declined: { label: "Declined", color: "bg-rose-50 text-rose-700 ring-rose-600/10", icon: XCircle },
};
const TEMPLATES = [
    { id: "modern", label: "Modern", desc: "Clean indigo gradient header" },
    { id: "minimal", label: "Minimal", desc: "Typographic, ultra-clean" },
    { id: "executive", label: "Executive", desc: "Navy premium two-column" },
    { id: "bold", label: "Bold", desc: "High-contrast full-bleed" },
    { id: "framed", label: "Blueprint", desc: "Technical mono grid" },
    { id: "darkcard", label: "Cyber", desc: "Dark terminal aesthetic" },
];
// ─────────────────────────────────────────────
// SUB COMPONENTS
// ─────────────────────────────────────────────
function ExpiryBadge({ expiryDate }) {
    if (!expiryDate)
        return _jsx("span", { className: "text-gray-400 text-xs", children: "\u2014" });
    const days = Math.ceil((new Date(expiryDate).getTime() - Date.now()) / 86400000);
    if (days < 0)
        return _jsx("span", { className: "inline-flex items-center text-[11px] font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-md", children: "Expired" });
    if (days === 0)
        return _jsx("span", { className: "inline-flex items-center text-[11px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-md", children: "Expires Today" });
    return _jsx("span", { className: "text-xs text-slate-600 font-semibold", children: formatDate(expiryDate) });
}
// ─────────────────────────────────────────────
// PRINT TEMPLATES
// ─────────────────────────────────────────────
function TemplateModern({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-white min-h-[900px] font-sans text-slate-800 text-xs", children: [_jsx("div", { className: "bg-gradient-to-br from-indigo-600 to-violet-700 p-10 text-white", children: _jsxs("div", { className: "flex justify-between items-start", children: [_jsxs("div", { className: "flex items-center gap-4", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-14 h-14 rounded-xl object-cover bg-white/20 p-1" }) : _jsx("div", { className: "w-14 h-14 bg-white/20 rounded-xl flex items-center justify-center font-black text-2xl", children: (company?.name || "Q")[0] }), _jsxs("div", { children: [_jsx("h2", { className: "text-xl font-black tracking-tight", children: company?.name || "Your Company" }), _jsx("p", { className: "text-indigo-200 text-[11px] mt-1", children: company?.address_line1 || "" }), _jsx("p", { className: "text-indigo-200 text-[11px]", children: company?.email || "" })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-[10px] uppercase tracking-[0.2em] text-indigo-300 font-bold", children: "Quotation" }), _jsx("div", { className: "text-3xl font-black mt-1", children: q.number }), _jsxs("div", { className: "text-indigo-200 text-[11px] mt-2", children: ["Issued ", formatDate(q.issue_date)] }), _jsxs("div", { className: "text-indigo-200 text-[11px]", children: ["Valid until ", formatDate(q.expiry_date || q.due_date)] })] })] }) }), _jsxs("div", { className: "p-10", children: [_jsxs("div", { className: "bg-slate-50 rounded-2xl p-6 mb-8 flex justify-between items-start border border-slate-100", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase font-black text-slate-400 tracking-widest mb-2", children: "Prepared For" }), _jsxs("div", { className: "text-base font-black text-slate-900", children: [q.salutation ? `${q.salutation} ` : "", q.client_name || "—"] }), q.client_email && _jsx("div", { className: "text-slate-500 text-[11px] mt-1", children: q.client_email }), q.client_phone && _jsx("div", { className: "text-slate-500 text-[11px]", children: q.client_phone })] }), _jsxs("div", { className: "text-right text-[11px] text-slate-500 space-y-1", children: [q.client_address && _jsx("div", { children: q.client_address }), q.client_vat_number && _jsxs("div", { children: ["VAT: ", q.client_vat_number] })] })] }), _jsxs("table", { className: "w-full border-collapse mb-8", children: [_jsx("thead", { children: _jsxs("tr", { className: "bg-slate-900 text-white text-[9px] uppercase tracking-widest font-black", children: [_jsx("th", { className: "p-4 text-left rounded-l-lg", children: "Description" }), _jsx("th", { className: "p-4 text-center w-16", children: "Qty" }), _jsx("th", { className: "p-4 text-right w-28", children: "Unit Price" }), _jsx("th", { className: "p-4 text-right w-28 rounded-r-lg", children: "Total" })] }) }), _jsx("tbody", { children: q.line_items?.map((item, i) => (_jsxs("tr", { className: i % 2 === 0 ? "bg-white" : "bg-slate-50/60", children: [_jsx("td", { className: "p-4 font-semibold text-slate-800", children: item.description }), _jsx("td", { className: "p-4 text-center text-slate-500 font-mono", children: item.quantity }), _jsx("td", { className: "p-4 text-right text-slate-600 font-mono", children: fmt(item.unit_price) }), _jsx("td", { className: "p-4 text-right font-black text-indigo-700 font-mono", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i))) })] }), _jsx("div", { className: "flex justify-end mb-8", children: _jsxs("div", { className: "w-72 bg-gradient-to-br from-indigo-600 to-violet-700 rounded-2xl p-6 text-white", children: [_jsx("div", { className: "text-[10px] uppercase tracking-widest font-black text-indigo-200 mb-2", children: "Total Amount" }), _jsx("div", { className: "text-3xl font-black", children: fmt(q.total_amount) }), _jsx("div", { className: "text-indigo-200 text-[11px] mt-2", children: q.currency })] }) }), q.notes && _jsxs("div", { className: "bg-amber-50 border border-amber-100 rounded-xl p-4 text-slate-600 text-[11px] leading-relaxed", children: [_jsx("strong", { className: "text-amber-800", children: "Notes:" }), " ", q.notes] })] })] }));
}
function TemplateMinimal({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-white min-h-[900px] font-serif text-slate-900 text-xs p-14", children: [_jsxs("div", { className: "flex justify-between items-start pb-8 border-b border-slate-900 mb-10", children: [_jsxs("div", { className: "flex items-center gap-4", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-10 h-10 object-contain" }) : null, _jsxs("div", { children: [_jsx("h2", { className: "text-lg font-bold tracking-tight", children: company?.name || "Your Company" }), _jsx("p", { className: "text-slate-400 text-[10px] mt-0.5", children: company?.address_line1 })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-[28px] font-bold tracking-tighter text-slate-200 -mb-2", children: "QUOTATION" }), _jsx("div", { className: "text-sm font-bold text-slate-900", children: q.number }), _jsx("div", { className: "text-slate-400 text-[10px] mt-1", children: formatDate(q.issue_date) })] })] }), _jsxs("div", { className: "grid grid-cols-2 gap-12 mb-10", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase tracking-[0.2em] text-slate-400 font-bold mb-3", children: "Bill To" }), _jsxs("div", { className: "text-base font-bold", children: [q.salutation ? `${q.salutation} ` : "", q.client_name] }), q.client_email && _jsx("div", { className: "text-slate-500 text-[11px] mt-1", children: q.client_email }), q.client_phone && _jsx("div", { className: "text-slate-500 text-[11px]", children: q.client_phone }), q.client_address && _jsx("div", { className: "text-slate-500 text-[11px]", children: q.client_address })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-[9px] uppercase tracking-[0.2em] text-slate-400 font-bold mb-3", children: "Valid Until" }), _jsx("div", { className: "text-base font-bold", children: formatDate(q.expiry_date || q.due_date) })] })] }), _jsxs("table", { className: "w-full mb-10", children: [_jsx("thead", { children: _jsxs("tr", { className: "border-b-2 border-slate-900 text-[9px] uppercase tracking-widest font-bold text-slate-400", children: [_jsx("th", { className: "py-3 text-left", children: "Item" }), _jsx("th", { className: "py-3 text-center", children: "Qty" }), _jsx("th", { className: "py-3 text-right", children: "Rate" }), _jsx("th", { className: "py-3 text-right", children: "Amount" })] }) }), _jsx("tbody", { className: "divide-y divide-slate-100", children: q.line_items?.map((item, i) => (_jsxs("tr", { children: [_jsx("td", { className: "py-4 font-medium", children: item.description }), _jsx("td", { className: "py-4 text-center text-slate-400 font-mono", children: item.quantity }), _jsx("td", { className: "py-4 text-right text-slate-500 font-mono", children: fmt(item.unit_price) }), _jsx("td", { className: "py-4 text-right font-bold font-mono", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i))) }), _jsx("tfoot", { children: _jsxs("tr", { className: "border-t-2 border-slate-900", children: [_jsx("td", { colSpan: 3, className: "pt-4 text-right text-[9px] uppercase tracking-widest font-black text-slate-400", children: "Total" }), _jsx("td", { className: "pt-4 text-right text-xl font-black", children: fmt(q.total_amount) })] }) })] }), q.notes && _jsx("div", { className: "text-slate-400 text-[11px] italic border-t border-slate-100 pt-6", children: q.notes })] }));
}
function TemplateExecutive({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-white min-h-[900px] font-sans text-xs flex", children: [_jsxs("div", { className: "w-56 bg-slate-900 text-white p-8 flex-shrink-0 flex flex-col", children: [_jsxs("div", { className: "mb-8", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-12 h-12 rounded-lg object-cover mb-4" }) : _jsx("div", { className: "w-12 h-12 bg-white/10 rounded-lg mb-4 flex items-center justify-center font-black text-xl", children: (company?.name || "Q")[0] }), _jsx("h2", { className: "text-sm font-black leading-tight", children: company?.name || "Your Company" }), _jsx("p", { className: "text-slate-400 text-[10px] mt-2", children: company?.address_line1 }), _jsx("p", { className: "text-slate-400 text-[10px]", children: company?.email })] }), _jsxs("div", { className: "border-t border-white/10 pt-6 space-y-4", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-500 font-bold", children: "Quotation" }), _jsx("div", { className: "text-sm font-black mt-1", children: q.number })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-500 font-bold", children: "Issued" }), _jsx("div", { className: "text-[11px] mt-1", children: formatDate(q.issue_date) })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-500 font-bold", children: "Valid Until" }), _jsx("div", { className: "text-[11px] mt-1", children: formatDate(q.expiry_date || q.due_date) })] }), _jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-500 font-bold", children: "Currency" }), _jsx("div", { className: "text-[11px] mt-1", children: q.currency })] })] }), _jsxs("div", { className: "mt-auto border-t border-white/10 pt-6", children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-2", children: "Total Value" }), _jsx("div", { className: "text-2xl font-black text-white", children: fmt(q.total_amount) })] })] }), _jsxs("div", { className: "flex-1 p-10", children: [_jsxs("div", { className: "mb-10", children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest text-slate-400 font-bold mb-3", children: "Prepared For" }), _jsxs("div", { className: "text-xl font-black text-slate-900", children: [q.salutation ? `${q.salutation} ` : "", q.client_name] }), q.client_email && _jsx("div", { className: "text-slate-500 text-[11px] mt-1", children: q.client_email }), q.client_phone && _jsx("div", { className: "text-slate-500 text-[11px]", children: q.client_phone }), q.client_address && _jsx("div", { className: "text-slate-500 text-[11px]", children: q.client_address })] }), _jsxs("table", { className: "w-full mb-8", children: [_jsx("thead", { children: _jsxs("tr", { className: "bg-slate-50 text-[9px] uppercase tracking-widest font-black text-slate-400", children: [_jsx("th", { className: "p-3 text-left", children: "Description" }), _jsx("th", { className: "p-3 text-center w-14", children: "Qty" }), _jsx("th", { className: "p-3 text-right w-24", children: "Unit" }), _jsx("th", { className: "p-3 text-right w-28", children: "Total" })] }) }), _jsx("tbody", { className: "divide-y divide-slate-50", children: q.line_items?.map((item, i) => (_jsxs("tr", { className: "hover:bg-slate-50/50", children: [_jsx("td", { className: "p-3 font-semibold text-slate-800", children: item.description }), _jsx("td", { className: "p-3 text-center text-slate-400 font-mono", children: item.quantity }), _jsx("td", { className: "p-3 text-right text-slate-500 font-mono", children: fmt(item.unit_price) }), _jsx("td", { className: "p-3 text-right font-black text-slate-900 font-mono", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i))) })] }), q.notes && _jsxs("div", { className: "bg-slate-50 border border-slate-100 rounded-xl p-4 text-slate-500 text-[11px] leading-relaxed", children: [_jsx("strong", { children: "Notes:" }), " ", q.notes] })] })] }));
}
function TemplateBold({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-white min-h-[900px] font-sans text-xs", children: [_jsx("div", { className: "bg-amber-400 p-10", children: _jsxs("div", { className: "flex justify-between items-start", children: [_jsxs("div", { className: "flex items-center gap-4", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-14 h-14 rounded object-cover border-2 border-black" }) : _jsx("div", { className: "w-14 h-14 bg-black flex items-center justify-center font-black text-amber-400 text-2xl", children: (company?.name || "Q")[0] }), _jsxs("div", { children: [_jsx("h2", { className: "text-xl font-black text-black uppercase tracking-tighter", children: company?.name || "Your Company" }), _jsx("p", { className: "text-black/60 text-[11px] mt-1", children: company?.address_line1 })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-5xl font-black text-black/10 tracking-tighter leading-none", children: "QUO" }), _jsx("div", { className: "text-lg font-black text-black -mt-2", children: q.number }), _jsx("div", { className: "text-black/70 text-[11px] mt-1", children: formatDate(q.issue_date) })] })] }) }), _jsxs("div", { className: "p-10", children: [_jsxs("div", { className: "border-4 border-black p-6 mb-8 flex justify-between items-start", children: [_jsxs("div", { children: [_jsx("div", { className: "text-[9px] uppercase font-black tracking-widest text-black/40 mb-1", children: "For" }), _jsxs("div", { className: "text-lg font-black", children: [q.salutation ? `${q.salutation} ` : "", q.client_name] }), q.client_email && _jsx("div", { className: "text-black/60 text-[11px]", children: q.client_email }), q.client_phone && _jsx("div", { className: "text-black/60 text-[11px]", children: q.client_phone })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-[9px] uppercase font-black tracking-widest text-black/40 mb-1", children: "Valid Until" }), _jsx("div", { className: "font-black text-base", children: formatDate(q.expiry_date || q.due_date) })] })] }), _jsxs("table", { className: "w-full border-collapse mb-8", children: [_jsx("thead", { children: _jsxs("tr", { className: "bg-black text-white text-[9px] uppercase tracking-widest font-black", children: [_jsx("th", { className: "p-4 text-left", children: "Item" }), _jsx("th", { className: "p-4 text-center w-14", children: "Qty" }), _jsx("th", { className: "p-4 text-right w-28", children: "Rate" }), _jsx("th", { className: "p-4 text-right w-28", children: "Total" })] }) }), _jsx("tbody", { className: "divide-y-2 divide-black/5", children: q.line_items?.map((item, i) => (_jsxs("tr", { className: i % 2 === 0 ? "" : "bg-amber-50", children: [_jsx("td", { className: "p-4 font-bold", children: item.description }), _jsx("td", { className: "p-4 text-center font-mono", children: item.quantity }), _jsx("td", { className: "p-4 text-right font-mono text-black/60", children: fmt(item.unit_price) }), _jsx("td", { className: "p-4 text-right font-black font-mono", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i))) })] }), _jsx("div", { className: "flex justify-end", children: _jsxs("div", { className: "bg-black text-white p-6 w-64", children: [_jsx("div", { className: "text-[9px] uppercase tracking-widest font-black text-white/40 mb-1", children: "Total" }), _jsx("div", { className: "text-3xl font-black text-amber-400", children: fmt(q.total_amount) })] }) }), q.notes && _jsx("div", { className: "mt-8 border-l-4 border-amber-400 pl-4 text-black/60 text-[11px] italic", children: q.notes })] })] }));
}
function TemplateBlueprint({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-white min-h-[900px] font-mono text-slate-900 text-xs border-4 border-slate-900 p-8", children: [_jsxs("div", { className: "border-b-2 border-slate-900 pb-6 mb-8 flex justify-between items-end", children: [_jsxs("div", { className: "flex items-center gap-3", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-10 h-10 border-2 border-slate-900 object-cover" }) : _jsx("div", { className: "w-10 h-10 bg-slate-900 text-white font-black flex items-center justify-center", children: (company?.name || "Q")[0] }), _jsxs("div", { children: [_jsx("div", { className: "text-[10px] font-black uppercase tracking-widest", children: "[BLUEPRINT ESTIMATE]" }), _jsx("h2", { className: "font-black text-sm uppercase", children: company?.name || "Your Company" })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "font-black text-sm bg-slate-900 text-white px-3 py-1", children: q.number }), _jsxs("div", { className: "text-slate-500 text-[10px] mt-1", children: ["ISSUED: ", formatDate(q.issue_date)] }), _jsxs("div", { className: "text-slate-500 text-[10px]", children: ["VALID_TO: ", formatDate(q.expiry_date || q.due_date)] })] })] }), _jsxs("div", { className: "border border-slate-300 bg-slate-50/50 p-4 grid grid-cols-2 gap-4 mb-8", children: [_jsxs("div", { children: [_jsx("span", { className: "text-[9px] text-slate-400 font-black uppercase block tracking-wider", children: "TAG_CLIENT:" }), _jsxs("span", { className: "font-black", children: [q.salutation ? `${q.salutation} ` : "", q.client_name] }), q.client_email && _jsx("span", { className: "block text-slate-500 text-[10px]", children: q.client_email }), q.client_phone && _jsx("span", { className: "block text-slate-500 text-[10px]", children: q.client_phone }), q.client_address && _jsx("span", { className: "block text-slate-500 text-[10px]", children: q.client_address })] }), _jsxs("div", { className: "text-right", children: [_jsx("span", { className: "text-[9px] text-slate-400 font-black uppercase block tracking-wider", children: "CURRENCY_CODE:" }), _jsx("span", { className: "font-black", children: q.currency })] })] }), _jsxs("div", { className: "border border-slate-900 rounded-sm overflow-hidden mb-8", children: [_jsxs("div", { className: "bg-slate-900 text-white text-[9px] uppercase font-black grid grid-cols-12 p-2.5 tracking-widest", children: [_jsx("span", { className: "col-span-6", children: "ITEM_SPECIFICATION" }), _jsx("span", { className: "col-span-2 text-center", children: "METRIC" }), _jsx("span", { className: "col-span-2 text-right", children: "UNIT_RATE" }), _jsx("span", { className: "col-span-2 text-right", children: "VAL_TOTAL" })] }), q.line_items?.map((item, i) => (_jsxs("div", { className: "grid grid-cols-12 p-2.5 border-b border-slate-200 bg-white items-center last:border-0", children: [_jsx("span", { className: "col-span-6 font-bold truncate", children: item.description }), _jsx("span", { className: "col-span-2 text-center text-slate-500", children: item.quantity }), _jsx("span", { className: "col-span-2 text-right text-slate-500", children: fmt(item.unit_price) }), _jsx("span", { className: "col-span-2 text-right font-black", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i)))] }), _jsxs("div", { className: "flex justify-between items-center border-2 border-slate-900 p-4 bg-slate-100/50", children: [_jsx("span", { className: "font-black uppercase tracking-wider text-sm", children: "SUM_TOTAL_VALUATION:" }), _jsx("span", { className: "text-xl font-black bg-slate-900 text-white px-4 py-2", children: fmt(q.total_amount) })] }), q.notes && _jsxs("div", { className: "mt-6 text-slate-500 text-[10px] border border-slate-200 p-3", children: [_jsx("span", { className: "font-black text-slate-700", children: "NOTES: " }), q.notes] })] }));
}
function TemplateCyber({ q, company, logo }) {
    const fmt = (v) => formatCurrency(parseFloat(String(v || 0)), q.currency);
    return (_jsxs("div", { className: "bg-slate-950 min-h-[900px] font-mono text-emerald-400 text-xs p-8 rounded-2xl", children: [_jsxs("div", { className: "border-b border-slate-800 pb-6 mb-8 flex justify-between items-start", children: [_jsxs("div", { className: "flex items-center gap-3", children: [logo ? _jsx("img", { src: logo, alt: "logo", className: "w-12 h-12 border border-emerald-500/30 rounded object-cover" }) : _jsx("div", { className: "w-12 h-12 border border-emerald-500/20 bg-emerald-500/10 flex items-center justify-center font-black text-white text-xl", children: (company?.name || "Q")[0] }), _jsxs("div", { children: [_jsx("div", { className: "text-[10px] text-slate-500 font-bold", children: "// CORPORATE_INSTANCE" }), _jsx("h2", { className: "text-sm font-bold text-white", children: company?.name || "Your Company" }), _jsx("div", { className: "text-slate-500 text-[10px]", children: company?.email })] })] }), _jsxs("div", { className: "text-right", children: [_jsx("div", { className: "text-[10px] text-slate-500", children: "DOCUMENT_TYPE: QUOTATION" }), _jsx("div", { className: "text-lg font-bold text-white mt-1", children: q.number }), _jsxs("div", { className: "text-slate-500 text-[10px] mt-1", children: ["TIMESTAMP: ", formatDate(q.issue_date)] }), _jsxs("div", { className: "text-slate-500 text-[10px]", children: ["TTL: ", formatDate(q.expiry_date || q.due_date)] })] })] }), _jsxs("div", { className: "bg-slate-900/60 border border-slate-800 rounded-xl p-5 mb-8 space-y-1.5", children: [_jsx("div", { className: "text-[9px] text-slate-500 font-bold uppercase tracking-widest mb-3", children: "# CLIENT_PARAMETERS" }), _jsxs("div", { children: [_jsx("span", { className: "text-emerald-500", children: "target_name" }), " = ", _jsxs("span", { className: "text-amber-300", children: ["\"", q.salutation ? `${q.salutation} ` : "", q.client_name, "\""] })] }), q.client_email && _jsxs("div", { children: [_jsx("span", { className: "text-slate-500", children: "email" }), " = ", _jsxs("span", { className: "text-slate-300", children: ["\"", q.client_email, "\""] })] }), q.client_phone && _jsxs("div", { children: [_jsx("span", { className: "text-slate-500", children: "phone" }), " = ", _jsxs("span", { className: "text-slate-300", children: ["\"", q.client_phone, "\""] })] }), q.client_address && _jsxs("div", { children: [_jsx("span", { className: "text-slate-500", children: "address" }), " = ", _jsxs("span", { className: "text-slate-300", children: ["\"", q.client_address, "\""] })] }), _jsxs("div", { children: [_jsx("span", { className: "text-slate-500", children: "currency" }), " = ", _jsxs("span", { className: "text-slate-300", children: ["\"", q.currency, "\""] })] })] }), _jsxs("div", { className: "space-y-2 mb-8", children: [_jsx("div", { className: "text-[9px] text-slate-500 font-bold uppercase tracking-widest mb-3", children: "# SCOPE_ITEMS[]" }), q.line_items?.map((item, i) => (_jsxs("div", { className: "bg-slate-900/40 border border-slate-900 rounded-lg p-4 flex justify-between items-center", children: [_jsxs("div", { children: [_jsx("div", { className: "text-white font-bold", children: item.description }), _jsxs("div", { className: "text-slate-500 text-[10px] mt-0.5", children: ["qty: ", item.quantity, " | rate: ", fmt(item.unit_price)] })] }), _jsx("div", { className: "text-emerald-300 font-bold text-sm", children: fmt(parseFloat(item.amount || String(item.quantity * item.unit_price))) })] }, i)))] }), _jsxs("div", { className: "border-t border-slate-800 pt-6 flex justify-between items-center", children: [_jsx("span", { className: "text-slate-500 font-bold uppercase tracking-widest text-[10px]", children: "NET_AGGREGATE_VALUE" }), _jsx("span", { className: "text-2xl font-black text-white", children: fmt(q.total_amount) })] }), q.notes && _jsxs("div", { className: "mt-6 text-slate-500 text-[10px] bg-slate-900/40 p-3 rounded-lg border border-slate-800", children: [_jsx("span", { className: "text-emerald-500", children: "// notes: " }), q.notes] })] }));
}
// ─────────────────────────────────────────────
// EXCEL ANALYSIS ENGINE
// ─────────────────────────────────────────────
function analyzeExcelFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            try {
                const data = new Uint8Array(e.target?.result);
                const workbook = XLSX.read(data, { type: "array" });
                const sheetName = workbook.SheetNames[0];
                const worksheet = workbook.Sheets[sheetName];
                const json = XLSX.utils.sheet_to_json(worksheet, { defval: "" });
                if (!json.length) {
                    reject(new Error("Empty sheet"));
                    return;
                }
                const headers = Object.keys(json[0]);
                const numericCols = [];
                const textCols = [];
                headers.forEach(h => {
                    const vals = json.map(r => r[h]).filter(v => v !== "" && v !== null);
                    const nums = vals.map(v => parseFloat(String(v))).filter(v => !isNaN(v));
                    if (nums.length / vals.length > 0.6)
                        numericCols.push(h);
                    else
                        textCols.push(h);
                });
                const stats = {};
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
            }
            catch (err) {
                reject(err);
            }
        };
        reader.readAsArrayBuffer(file);
    });
}
// ─────────────────────────────────────────────
// AI ANALYSIS COMPONENT
// ─────────────────────────────────────────────
function ExcelAnalysisPanel({ onClose }) {
    const [analysis, setAnalysis] = useState(null);
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);
    const [aiReport, setAiReport] = useState("");
    const [dragging, setDragging] = useState(false);
    const [fileName, setFileName] = useState("");
    const fileRef = useRef(null);
    const processFile = async (file) => {
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
            const text = data.content?.map((b) => b.text || "").join("") || "";
            setAiReport(text);
        }
        catch (e) {
            console.error(e);
        }
        finally {
            setLoading(false);
            setAiLoading(false);
        }
    };
    const handleDrop = (e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file)
            processFile(file);
    };
    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload?.length) {
            return (_jsxs("div", { className: "bg-slate-900 border border-slate-700 rounded-xl px-4 py-3 text-xs text-white shadow-2xl", children: [_jsx("p", { className: "font-bold text-slate-300 mb-1", children: label }), payload.map((p, i) => (_jsxs("p", { style: { color: p.color }, children: [p.name, ": ", _jsx("span", { className: "font-black", children: typeof p.value === "number" ? p.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : p.value })] }, i)))] }));
        }
        return null;
    };
    return (_jsx("div", { className: "fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center overflow-y-auto py-8 px-4", children: _jsxs("div", { className: "bg-white rounded-3xl shadow-2xl w-full max-w-6xl", children: [_jsxs("div", { className: "flex items-center justify-between p-6 border-b border-gray-100", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: "w-10 h-10 bg-gradient-to-br from-violet-600 to-indigo-600 rounded-xl flex items-center justify-center", children: _jsx(BarChart3, { className: "w-5 h-5 text-white" }) }), _jsxs("div", { children: [_jsx("h2", { className: "text-lg font-black text-slate-900", children: "Excel Intelligence Analysis" }), _jsx("p", { className: "text-xs text-slate-400", children: fileName || "Upload a spreadsheet for AI-powered insights" })] })] }), _jsx("button", { onClick: onClose, className: "p-2 hover:bg-gray-100 rounded-xl transition-colors", children: _jsx(X, { className: "w-5 h-5 text-slate-500" }) })] }), _jsxs("div", { className: "p-6", children: [!analysis && (_jsxs("div", { onDragOver: e => { e.preventDefault(); setDragging(true); }, onDragLeave: () => setDragging(false), onDrop: handleDrop, onClick: () => fileRef.current?.click(), className: cn("border-2 border-dashed rounded-2xl p-16 text-center cursor-pointer transition-all", dragging ? "border-indigo-500 bg-indigo-50" : "border-gray-200 hover:border-indigo-300 hover:bg-gray-50"), children: [loading ? (_jsxs("div", { className: "flex flex-col items-center gap-3", children: [_jsx("div", { className: "w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" }), _jsx("p", { className: "text-sm font-bold text-indigo-600", children: "Analyzing spreadsheet..." })] })) : (_jsxs(_Fragment, { children: [_jsx(FileSpreadsheet, { className: "w-14 h-14 text-gray-300 mx-auto mb-4" }), _jsx("p", { className: "text-base font-black text-slate-700", children: "Drop your Excel or CSV file here" }), _jsx("p", { className: "text-sm text-slate-400 mt-1", children: "or click to browse \u2014 .xlsx, .xls, .csv supported" })] })), _jsx("input", { ref: fileRef, type: "file", accept: ".xlsx,.xls,.csv", className: "hidden", onChange: e => { const f = e.target.files?.[0]; if (f)
                                        processFile(f); } })] })), analysis && (_jsxs("div", { className: "space-y-6", children: [_jsx("div", { className: "grid grid-cols-2 sm:grid-cols-4 gap-4", children: [
                                        { label: "Total Rows", value: analysis.summary.totalRows.toLocaleString(), icon: Layers, color: "from-indigo-500 to-violet-600" },
                                        { label: "Columns", value: analysis.summary.totalCols, icon: Activity, color: "from-cyan-500 to-blue-600" },
                                        { label: "Numeric Fields", value: analysis.summary.numericColumns.length, icon: TrendingUp, color: "from-emerald-500 to-teal-600" },
                                        { label: "Data Sheets", value: analysis.summary.sheets.length, icon: FileSpreadsheet, color: "from-amber-500 to-orange-600" },
                                    ].map((c, i) => (_jsxs("div", { className: `bg-gradient-to-br ${c.color} rounded-2xl p-5 text-white`, children: [_jsx(c.icon, { className: "w-5 h-5 mb-2 opacity-80" }), _jsx("div", { className: "text-2xl font-black", children: c.value }), _jsx("div", { className: "text-[10px] font-bold uppercase tracking-wider opacity-80 mt-1", children: c.label })] }, i))) }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-6", children: [_jsxs("div", { className: "bg-slate-50 rounded-2xl p-5 border border-slate-100", children: [_jsxs("h3", { className: "text-sm font-black text-slate-800 mb-4 flex items-center gap-2", children: [_jsx(BarChart3, { className: "w-4 h-4 text-indigo-600" }), " Value Distribution"] }), _jsx(ResponsiveContainer, { width: "100%", height: 220, children: _jsxs(BarChart, { data: analysis.chartData.bar, margin: { top: 5, right: 5, left: 0, bottom: 30 }, children: [_jsx(CartesianGrid, { strokeDasharray: "3 3", stroke: "#e2e8f0" }), _jsx(XAxis, { dataKey: "name", tick: { fontSize: 9, fill: "#94a3b8", fontWeight: 700 }, angle: -30, textAnchor: "end", interval: 0 }), _jsx(YAxis, { tick: { fontSize: 9, fill: "#94a3b8" } }), _jsx(Tooltip, { content: _jsx(CustomTooltip, {}) }), _jsx(Bar, { dataKey: "value", fill: "#6366f1", radius: [4, 4, 0, 0], children: analysis.chartData.bar.map((_, i) => _jsx(Cell, { fill: CHART_COLORS[i % CHART_COLORS.length] }, i)) })] }) })] }), _jsxs("div", { className: "bg-slate-50 rounded-2xl p-5 border border-slate-100", children: [_jsxs("h3", { className: "text-sm font-black text-slate-800 mb-4 flex items-center gap-2", children: [_jsx(TrendingUp, { className: "w-4 h-4 text-emerald-600" }), " Data Trend"] }), _jsx(ResponsiveContainer, { width: "100%", height: 220, children: _jsxs(AreaChart, { data: analysis.chartData.trend, margin: { top: 5, right: 5, left: 0, bottom: 30 }, children: [_jsx("defs", { children: _jsxs("linearGradient", { id: "trendGrad", x1: "0", y1: "0", x2: "0", y2: "1", children: [_jsx("stop", { offset: "5%", stopColor: "#6366f1", stopOpacity: 0.3 }), _jsx("stop", { offset: "95%", stopColor: "#6366f1", stopOpacity: 0 })] }) }), _jsx(CartesianGrid, { strokeDasharray: "3 3", stroke: "#e2e8f0" }), _jsx(XAxis, { dataKey: "name", tick: { fontSize: 9, fill: "#94a3b8", fontWeight: 700 }, angle: -30, textAnchor: "end", interval: 0 }), _jsx(YAxis, { tick: { fontSize: 9, fill: "#94a3b8" } }), _jsx(Tooltip, { content: _jsx(CustomTooltip, {}) }), _jsx(Area, { type: "monotone", dataKey: "value", stroke: "#6366f1", strokeWidth: 2.5, fill: "url(#trendGrad)", dot: { fill: "#6366f1", r: 3 } })] }) })] })] }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-3 gap-6", children: [_jsxs("div", { className: "bg-slate-50 rounded-2xl p-5 border border-slate-100", children: [_jsxs("h3", { className: "text-sm font-black text-slate-800 mb-4 flex items-center gap-2", children: [_jsx(Activity, { className: "w-4 h-4 text-violet-600" }), " Column Share"] }), _jsx(ResponsiveContainer, { width: "100%", height: 200, children: _jsxs(PieChart, { children: [_jsx(Pie, { data: analysis.chartData.distribution, cx: "50%", cy: "50%", outerRadius: 80, dataKey: "value", label: ({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`, labelLine: false, fontSize: 8, children: analysis.chartData.distribution.map((entry, i) => _jsx(Cell, { fill: entry.color }, i)) }), _jsx(Tooltip, { content: _jsx(CustomTooltip, {}) })] }) })] }), _jsxs("div", { className: "lg:col-span-2 bg-slate-50 rounded-2xl p-5 border border-slate-100", children: [_jsxs("h3", { className: "text-sm font-black text-slate-800 mb-4 flex items-center gap-2", children: [_jsx(DollarSign, { className: "w-4 h-4 text-amber-600" }), " Column Statistics"] }), _jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "w-full text-xs", children: [_jsx("thead", { children: _jsxs("tr", { className: "text-[9px] uppercase font-black text-slate-400 tracking-wider border-b border-slate-200", children: [_jsx("th", { className: "text-left pb-2", children: "Column" }), _jsx("th", { className: "text-right pb-2", children: "Min" }), _jsx("th", { className: "text-right pb-2", children: "Max" }), _jsx("th", { className: "text-right pb-2", children: "Avg" }), _jsx("th", { className: "text-right pb-2", children: "Sum" })] }) }), _jsx("tbody", { className: "divide-y divide-slate-100", children: Object.entries(analysis.stats).map(([col, s]) => (_jsxs("tr", { className: "hover:bg-white transition-colors", children: [_jsx("td", { className: "py-2 font-bold text-slate-700 truncate max-w-[120px]", children: col }), _jsx("td", { className: "py-2 text-right font-mono text-slate-500", children: s.min.toLocaleString(undefined, { maximumFractionDigits: 2 }) }), _jsx("td", { className: "py-2 text-right font-mono text-slate-500", children: s.max.toLocaleString(undefined, { maximumFractionDigits: 2 }) }), _jsx("td", { className: "py-2 text-right font-mono text-indigo-600 font-bold", children: s.avg.toLocaleString(undefined, { maximumFractionDigits: 2 }) }), _jsx("td", { className: "py-2 text-right font-mono font-black text-slate-900", children: s.sum.toLocaleString(undefined, { maximumFractionDigits: 2 }) })] }, col))) })] }) })] })] }), _jsxs("div", { className: "bg-gradient-to-br from-indigo-950 to-slate-950 rounded-2xl p-6 text-white", children: [_jsxs("div", { className: "flex items-center gap-3 mb-4", children: [_jsx("div", { className: "w-8 h-8 bg-indigo-500/20 rounded-lg flex items-center justify-center", children: _jsx(Sparkles, { className: "w-4 h-4 text-indigo-300" }) }), _jsx("h3", { className: "text-sm font-black", children: "AI Executive Report" }), aiLoading && _jsx("div", { className: "w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin ml-auto" })] }), aiLoading && !aiReport && (_jsx("div", { className: "space-y-2", children: [100, 80, 90, 70, 85].map((w, i) => _jsx("div", { className: "h-3 bg-white/5 rounded-full animate-pulse", style: { width: `${w}%` } }, i)) })), aiReport && (_jsx("div", { className: "text-slate-300 text-xs leading-relaxed whitespace-pre-wrap", children: aiReport }))] }), _jsx("div", { className: "flex justify-end", children: _jsxs("button", { onClick: () => { setAnalysis(null); setAiReport(""); setFileName(""); }, className: "flex items-center gap-2 text-xs font-bold text-slate-400 hover:text-slate-700 transition-colors", children: [_jsx(RefreshCw, { className: "w-3.5 h-3.5" }), " Analyze another file"] }) })] }))] })] }) }));
}
// ─────────────────────────────────────────────
// TEMPLATE PICKER MODAL
// ─────────────────────────────────────────────
function TemplatePicker({ current, logo, onLogoChange, onSelect, onClose, q, company }) {
    const fileRef = useRef(null);
    const renderMini = (id) => {
        const props = { q, company, logo };
        const map = {
            modern: _jsx(TemplateModern, { ...props }),
            minimal: _jsx(TemplateMinimal, { ...props }),
            executive: _jsx(TemplateExecutive, { ...props }),
            bold: _jsx(TemplateBold, { ...props }),
            framed: _jsx(TemplateBlueprint, { ...props }),
            darkcard: _jsx(TemplateCyber, { ...props }),
        };
        return map[id] || null;
    };
    return (_jsx("div", { className: "fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4", children: _jsxs("div", { className: "bg-white rounded-3xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col", children: [_jsxs("div", { className: "flex items-center justify-between p-6 border-b border-gray-100", children: [_jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: "w-9 h-9 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-xl flex items-center justify-center", children: _jsx(Palette, { className: "w-4 h-4 text-white" }) }), _jsx("h2", { className: "text-base font-black text-slate-900", children: "Choose Quotation Template" })] }), _jsxs("div", { className: "flex items-center gap-3", children: [_jsxs("button", { onClick: () => fileRef.current?.click(), className: "flex items-center gap-2 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-2 rounded-xl transition-colors", children: [_jsx(Upload, { className: "w-3.5 h-3.5" }), " ", logo ? "Change Logo" : "Upload Logo"] }), _jsx("input", { ref: fileRef, type: "file", accept: "image/*", className: "hidden", onChange: e => {
                                        const f = e.target.files?.[0];
                                        if (f)
                                            onLogoChange(URL.createObjectURL(f));
                                    } }), _jsx("button", { onClick: onClose, className: "p-2 hover:bg-gray-100 rounded-xl transition-colors", children: _jsx(X, { className: "w-4 h-4 text-slate-500" }) })] })] }), _jsx("div", { className: "overflow-y-auto p-6 grid grid-cols-2 lg:grid-cols-3 gap-5", children: TEMPLATES.map(t => (_jsxs("div", { onClick: () => onSelect(t.id), className: cn("relative cursor-pointer rounded-2xl overflow-hidden border-2 transition-all hover:shadow-xl group", current === t.id ? "border-indigo-500 shadow-lg shadow-indigo-100" : "border-gray-100 hover:border-indigo-200"), children: [_jsx("div", { className: "h-52 overflow-hidden pointer-events-none", children: _jsx("div", { className: "scale-[0.35] origin-top-left w-[285%]", children: renderMini(t.id) }) }), _jsxs("div", { className: "p-3 bg-white border-t border-gray-100 flex items-center justify-between", children: [_jsxs("div", { children: [_jsx("div", { className: "text-xs font-black text-slate-900", children: t.label }), _jsx("div", { className: "text-[10px] text-slate-400", children: t.desc })] }), current === t.id && _jsx("div", { className: "w-5 h-5 bg-indigo-600 rounded-full flex items-center justify-center flex-shrink-0", children: _jsx(Check, { className: "w-3 h-3 text-white" }) })] })] }, t.id))) })] }) }));
}
// ─────────────────────────────────────────────
// PRINT / DOCUMENT VIEW
// ─────────────────────────────────────────────
function DocumentView({ q, company, logo, template, onBack }) {
    const [showTemplatePicker, setShowTemplatePicker] = useState(false);
    const [activeTemplate, setActiveTemplate] = useState(template);
    const [currentLogo, setCurrentLogo] = useState(logo);
    const props = { q, company, logo: currentLogo };
    const templateMap = {
        modern: _jsx(TemplateModern, { ...props }),
        minimal: _jsx(TemplateMinimal, { ...props }),
        executive: _jsx(TemplateExecutive, { ...props }),
        bold: _jsx(TemplateBold, { ...props }),
        framed: _jsx(TemplateBlueprint, { ...props }),
        darkcard: _jsx(TemplateCyber, { ...props }),
    };
    return (_jsxs("div", { className: "p-4 sm:p-8 max-w-5xl mx-auto min-h-screen bg-gray-50 animate-fade-in print:p-0 print:bg-white", children: [_jsxs("div", { className: "flex items-center justify-between border-b border-gray-200 pb-4 mb-6 print:hidden bg-white rounded-2xl p-4 shadow-sm", children: [_jsxs("button", { onClick: onBack, className: "flex items-center gap-2 text-sm text-gray-500 hover:text-slate-900 font-bold transition-colors", children: [_jsx(ArrowLeft, { className: "w-4 h-4" }), " Back to Pipeline"] }), _jsxs("div", { className: "flex items-center gap-3", children: [_jsxs("button", { onClick: () => setShowTemplatePicker(true), className: "flex items-center gap-2 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-xl transition-colors", children: [_jsx(Palette, { className: "w-3.5 h-3.5" }), " Change Template"] }), _jsxs("button", { onClick: () => window.print(), className: "flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-sm", children: [_jsx(Printer, { className: "w-4 h-4" }), " Print / Export PDF"] })] })] }), _jsx("div", { className: "shadow-2xl rounded-2xl overflow-hidden print:shadow-none print:rounded-none", children: templateMap[activeTemplate] || templateMap.modern }), showTemplatePicker && (_jsx(TemplatePicker, { current: activeTemplate, logo: currentLogo, onLogoChange: setCurrentLogo, onSelect: id => { setActiveTemplate(id); setShowTemplatePicker(false); }, onClose: () => setShowTemplatePicker(false), q: q, company: company }))] }));
}
// ─────────────────────────────────────────────
// MAIN PAGE
// ─────────────────────────────────────────────
export default function QuotationsPage() {
    const qc = useQueryClient();
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("");
    const [documentViewTarget, setDocumentViewTarget] = useState(null);
    const [activeTemplate, setActiveTemplate] = useState("modern");
    const [uploadedLogo, setUploadedLogo] = useState(null);
    const [showExcelAnalysis, setShowExcelAnalysis] = useState(false);
    const [showTemplatePicker, setShowTemplatePicker] = useState(false);
    const logoFileRef = useRef(null);
    const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
    const company = companiesData?.data?.results?.[0];
    const { data, isLoading } = useQuery({
        queryKey: ["quotations", search, statusFilter],
        queryFn: () => quotationsApi.list({ ...(search && { search }), ...(statusFilter && { status: statusFilter }) }),
    });
    const deleteMutation = useMutation({
        mutationFn: (id) => quotationsApi.delete(id),
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
        return (_jsx(DocumentView, { q: documentViewTarget, company: company, logo: logo, template: activeTemplate, onBack: () => setDocumentViewTarget(null) }));
    }
    return (_jsxs("div", { className: "p-4 sm:p-8 bg-gray-50/30 min-h-screen print:hidden", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8", children: [_jsxs("div", { children: [_jsx("h1", { className: "text-2xl font-black text-slate-900 tracking-tight", children: "Quotations Pipeline" }), _jsxs("p", { className: "text-gray-400 text-xs mt-0.5", children: [stats.total, " total proposals"] })] }), _jsxs("div", { className: "flex items-center gap-3 flex-wrap", children: [_jsxs("button", { onClick: () => logoFileRef.current?.click(), className: "flex items-center gap-2 text-xs font-bold text-slate-600 bg-white border border-gray-200 hover:border-indigo-300 hover:text-indigo-600 px-3 py-2 rounded-xl transition-all shadow-xs", children: [_jsx(Upload, { className: "w-3.5 h-3.5" }), uploadedLogo ? "Logo Uploaded ✓" : "Upload Logo"] }), _jsx("input", { ref: logoFileRef, type: "file", accept: "image/*", className: "hidden", onChange: e => {
                                    const f = e.target.files?.[0];
                                    if (f)
                                        setUploadedLogo(URL.createObjectURL(f));
                                } }), _jsxs("button", { onClick: () => setShowTemplatePicker(true), className: "flex items-center gap-2 text-xs font-bold text-slate-600 bg-white border border-gray-200 hover:border-indigo-300 hover:text-indigo-600 px-3 py-2 rounded-xl transition-all shadow-xs", children: [_jsx(Palette, { className: "w-3.5 h-3.5" }), " Templates"] }), _jsxs("button", { onClick: () => setShowExcelAnalysis(true), className: "flex items-center gap-2 text-xs font-bold text-violet-700 bg-violet-50 hover:bg-violet-100 border border-violet-200 px-3 py-2 rounded-xl transition-all", children: [_jsx(BarChart3, { className: "w-3.5 h-3.5" }), " Analyze Excel"] }), _jsxs(Link, { to: "/quotations/new", className: "flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-sm transition-all", children: [_jsx(Plus, { className: "w-4 h-4" }), " New Proposal"] })] })] }), _jsx("div", { className: "grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6", children: [
                    { label: "Total Quotes", value: stats.total, color: "bg-white text-slate-900 border-gray-100" },
                    { label: "Awaiting Reply", value: stats.pending, color: "bg-white text-blue-600 border-gray-100" },
                    { label: "Accepted Deals", value: stats.accepted, color: "bg-white text-emerald-600 border-gray-100" },
                    { label: "Pipeline Worth", value: formatCurrency(stats.totalValue, company?.default_currency ?? "KES"), color: "bg-slate-900 text-white border-transparent shadow-md" },
                ].map((s, idx) => (_jsxs("div", { className: cn("rounded-2xl p-5 border transition-all hover:scale-[1.01]", s.color), children: [_jsx("p", { className: "text-[10px] sm:text-xs font-bold uppercase tracking-wider opacity-70 truncate", children: s.label }), _jsx("p", { className: "text-xl sm:text-2xl font-black mt-1.5 truncate tracking-tight", children: s.value })] }, idx))) }), _jsxs("div", { className: "flex flex-col sm:flex-row gap-3 mb-6 bg-white p-4 rounded-xl border border-gray-100 shadow-xs", children: [_jsxs("div", { className: "relative flex-1", children: [_jsx(Search, { className: "absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" }), _jsx("input", { value: search, onChange: e => setSearch(e.target.value), placeholder: "Search proposals...", className: "w-full pl-9 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-indigo-500 bg-slate-50/50" })] }), _jsxs("select", { value: statusFilter, onChange: e => setStatusFilter(e.target.value), className: "border border-gray-200 rounded-xl px-3 py-2 text-sm focus:outline-none bg-white font-semibold text-slate-600", children: [_jsx("option", { value: "", children: "All statuses" }), Object.entries(STATUS_META).map(([k, v]) => _jsx("option", { value: k, children: v.label }, k))] })] }), _jsx("div", { className: "bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden", children: _jsx("div", { className: "overflow-x-auto", children: _jsxs("table", { className: "w-full min-w-[800px] table-auto border-collapse text-left", children: [_jsx("thead", { children: _jsxs("tr", { className: "border-b border-gray-100 bg-slate-50/60 text-gray-400 font-bold text-[11px] uppercase tracking-wider", children: [_jsx("th", { className: "px-6 py-4", children: "Reference" }), _jsx("th", { className: "px-6 py-4", children: "Client" }), _jsx("th", { className: "px-6 py-4 text-right", children: "Value" }), _jsx("th", { className: "px-6 py-4 text-center", children: "Status" }), _jsx("th", { className: "px-6 py-4", children: "Expires" }), _jsx("th", { className: "px-6 py-4 w-12" })] }) }), _jsxs("tbody", { className: "divide-y divide-gray-50 font-medium text-slate-700", children: [isLoading && (_jsx("tr", { children: _jsx("td", { colSpan: 6, className: "px-6 py-12 text-center text-gray-400 animate-pulse", children: "Loading pipeline..." }) })), !isLoading && quotations.length === 0 && (_jsx("tr", { children: _jsx("td", { colSpan: 6, className: "px-6 py-16 text-center text-gray-400 text-sm", children: "No proposals found." }) })), quotations.map((q) => {
                                        const sm = STATUS_META[q.status] ?? STATUS_META.draft;
                                        const StatusIcon = sm.icon;
                                        return (_jsxs("tr", { className: "hover:bg-slate-50/40 transition-colors group text-xs sm:text-sm", children: [_jsxs("td", { className: "px-6 py-4", children: [_jsxs("button", { type: "button", onClick: () => setDocumentViewTarget(q), className: "font-bold text-indigo-600 hover:underline flex items-center gap-1.5", children: [q.number, " ", _jsx(Eye, { className: "w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" })] }), _jsx("p", { className: "text-[10px] text-gray-400 mt-0.5", children: formatDate(q.issue_date) })] }), _jsxs("td", { className: "px-6 py-4 text-slate-900 font-bold", children: [q.salutation ? `${q.salutation} ` : "", q.client_name || "—"] }), _jsx("td", { className: "px-6 py-4 text-right text-slate-900 font-black", children: formatCurrency(q.total_amount, q.currency) }), _jsx("td", { className: "px-6 py-4 text-center", children: _jsxs("span", { className: cn("inline-flex items-center gap-1 text-[11px] font-bold px-3 py-1 rounded-full ring-1 ring-inset capitalize", sm.color), children: [_jsx(StatusIcon, { className: "w-3 h-3" }), " ", sm.label] }) }), _jsx("td", { className: "px-6 py-4", children: _jsx(ExpiryBadge, { expiryDate: q.expiry_date || q.due_date }) }), _jsx("td", { className: "px-6 py-4 text-center", children: _jsx("button", { type: "button", onClick: () => { if (confirm("Delete this proposal?"))
                                                            deleteMutation.mutate(q.id); }, className: "p-1.5 text-gray-400 hover:text-rose-500 rounded-lg hover:bg-rose-50 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity", children: _jsx(Trash2, { className: "w-4 h-4" }) }) })] }, q.id));
                                    })] })] }) }) }), showExcelAnalysis && _jsx(ExcelAnalysisPanel, { onClose: () => setShowExcelAnalysis(false) }), showTemplatePicker && (_jsx(TemplatePicker, { current: activeTemplate, logo: logo, onLogoChange: setUploadedLogo, onSelect: id => { setActiveTemplate(id); setShowTemplatePicker(false); }, onClose: () => setShowTemplatePicker(false), q: quotations[0] || { number: "QUO-001", client_name: "Sample Client", line_items: [{ description: "Service Item", quantity: 1, unit_price: 5000, amount: "5000" }], total_amount: "5000", currency: "KES", issue_date: new Date().toISOString(), expiry_date: null, due_date: new Date(Date.now() + 30 * 86400000).toISOString() }, company: company }))] }));
}
