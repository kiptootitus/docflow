import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import { Sparkles, Upload, FileText, Image, Loader2, ClipboardCheck, Terminal, Eye, FileSpreadsheet, Receipt, Building, User, Phone, MapPin } from "lucide-react";
import { aiApi, companiesApi } from "@/lib/api";
import { cn } from "@/lib/utils";
export default function AiReviewPage() {
    const qc = useQueryClient();
    const navigate = useNavigate();
    // Custom manual/override parameters fields state parameters
    const [companyName, setCompanyName] = useState("");
    const [companyAddress, setCompanyAddress] = useState("");
    const [companyCity, setCompanyCity] = useState("");
    const [locationNumber, setLocationNumber] = useState("");
    const [salutation, setSalutation] = useState("Mr.");
    const [clientName, setClientName] = useState("");
    const [aiInstructions, setAiInstructions] = useState("");
    const [selectedReview, setSelectedReview] = useState(null);
    const [exportFormat, setExportFormat] = useState("pdf");
    const [isExporting, setIsExporting] = useState(false);
    const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
    const company = companiesData?.data?.results?.[0];
    const { data: reviewsData, isLoading: loadingHistory } = useQuery({
        queryKey: ["ai-reviews", company?.id],
        queryFn: () => aiApi.listReviews(company?.id),
        enabled: Boolean(company?.id),
    });
    const reviews = reviewsData ?? [];
    const updateFormState = (data) => {
        if (data.extracted_company_name)
            setCompanyName(data.extracted_company_name);
        if (data.extracted_company_address)
            setCompanyAddress(data.extracted_company_address);
        if (data.extracted_company_city)
            setCompanyCity(data.extracted_company_city);
        if (data.extracted_company_location_number)
            setLocationNumber(data.extracted_company_location_number);
        if (data.extracted_salutation)
            setSalutation(data.extracted_salutation);
        if (data.extracted_client_name)
            setClientName(data.extracted_client_name);
    };
    const reviewMutation = useMutation({
        mutationFn: (file) => {
            const fd = new FormData();
            if (file)
                fd.append("file", file);
            // Inject manual context instructions for smart data creation overrides
            const directiveSummary = `
        ${aiInstructions}. 
        Explicit context setup: Company Name: ${companyName}, Address: ${companyAddress}, City: ${companyCity}, Phone/Location number: ${locationNumber}, Client Prefix: ${salutation}, Client Target Name: ${clientName}
      `;
            fd.append("instructions", directiveSummary.trim());
            if (company?.id)
                fd.append("company", company.id);
            return aiApi.reviewContract(fd);
        },
        onSuccess: (res) => {
            qc.invalidateQueries({ queryKey: ["ai-reviews"] });
            setSelectedReview(res.data);
            updateFormState(res.data);
        },
        onError: (err) => {
            alert(`AI Execution Error: ${err.response?.data?.detail || "Failed to analyze layout configuration metrics."}`);
        }
    });
    const onDrop = useCallback((files) => {
        if (files[0] && company)
            reviewMutation.mutate(files[0]);
    }, [company, reviewMutation]);
    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        onDrop,
        accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg", ".jpeg", ".webp"] },
        maxFiles: 1,
    });
    const handleRouteConversion = (targetRoute) => {
        const prefillPayload = {
            ...selectedReview,
            extracted_company_name: companyName,
            extracted_company_address: companyAddress,
            extracted_company_city: companyCity,
            extracted_company_location_number: locationNumber,
            extracted_salutation: salutation,
            extracted_client_name: clientName
        };
        navigate(targetRoute, { state: { prefill: prefillPayload } });
    };
    return (_jsxs("div", { className: "p-4 sm:p-8 bg-slate-50/60 min-h-screen flex flex-col font-sans text-slate-800 antialiased", children: [_jsx("div", { className: "mb-6 bg-white p-6 rounded-2xl border border-slate-100 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4", children: _jsxs("div", { children: [_jsxs("h1", { className: "text-xl sm:text-2xl font-bold tracking-tight text-slate-950 flex items-center gap-2", children: [_jsx("div", { className: "p-2 bg-indigo-600 rounded-xl text-white shadow-xs", children: _jsx(Sparkles, { className: "w-5 h-5 fill-indigo-200" }) }), "Smart Automated Document Workspace"] }), _jsx("p", { className: "text-slate-400 text-xs sm:text-sm mt-0.5", children: "Drop invoice image logs or supply parameters manually below to experience instant AI synthesis." })] }) }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 items-start", children: [_jsxs("div", { className: "space-y-6 lg:col-span-1", children: [_jsxs("div", { className: "bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-4", children: [_jsxs("h3", { className: "font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5", children: [_jsx(Building, { className: "w-3.5 h-3.5 text-indigo-500" }), " Company Parameters"] }), _jsxs("div", { className: "space-y-3", children: [_jsxs("div", { children: [_jsx("label", { className: "text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1", children: "Company Name" }), _jsx("input", { type: "text", value: companyName, onChange: e => setCompanyName(e.target.value), placeholder: "e.g. DocFlow Global Ltd", className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none focus:border-indigo-500 bg-slate-50/50" })] }), _jsxs("div", { className: "grid grid-cols-2 gap-2", children: [_jsxs("div", { children: [_jsx("label", { className: "text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1", children: "Street Address" }), _jsx("input", { type: "text", value: companyAddress, onChange: e => setCompanyAddress(e.target.value), placeholder: "Mombasa Road", className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" })] }), _jsxs("div", { children: [_jsx("label", { className: "text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1", children: "City" }), _jsx("input", { type: "text", value: companyCity, onChange: e => setCompanyCity(e.target.value), placeholder: "Nairobi", className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" })] })] }), _jsxs("div", { children: [_jsxs("label", { className: "text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1 flex items-center gap-0.5", children: [_jsx(Phone, { className: "w-2.5 h-2.5" }), " Contact Location Number"] }), _jsx("input", { type: "text", value: locationNumber, onChange: e => setLocationNumber(e.target.value), placeholder: "e.g. +254 700 000 000", className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" })] })] }), _jsxs("div", { className: "border-t border-slate-100 pt-4 space-y-3", children: [_jsxs("h3", { className: "font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5", children: [_jsx(User, { className: "w-3.5 h-3.5 text-violet-500" }), " Target Assignee"] }), _jsxs("div", { className: "grid grid-cols-3 gap-2", children: [_jsxs("div", { children: [_jsx("label", { className: "text-[10px] font-bold text-slate-400 uppercase block mb-1", children: "Prefix" }), _jsx("select", { value: salutation, onChange: e => setSalutation(e.target.value), className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white focus:outline-none", children: ["Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Messrs."].map(p => _jsx("option", { value: p, children: p }, p)) })] }), _jsxs("div", { className: "col-span-2", children: [_jsx("label", { className: "text-[10px] font-bold text-slate-400 uppercase block mb-1", children: "Client Name" }), _jsx("input", { type: "text", value: clientName, onChange: e => setClientName(e.target.value), placeholder: "John Doe Enterprise", className: "w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" })] })] })] })] }), _jsxs("div", { className: "bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-3", children: [_jsxs("h3", { className: "font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5", children: [_jsx(Terminal, { className: "w-3.5 h-3.5 text-emerald-500" }), " Natural Language Directives"] }), _jsx("textarea", { value: aiInstructions, onChange: (e) => setAiInstructions(e.target.value), rows: 3, placeholder: "Type your instruction or budget criteria here (e.g. 'Write a quotation for 5 laptop replacement screens with 16% tax rate...')", className: "w-full border border-slate-200 rounded-xl p-3 text-xs focus:outline-none focus:border-indigo-500 bg-slate-50/50 resize-none font-medium text-slate-700" }), _jsxs("button", { type: "button", onClick: () => reviewMutation.mutate(), disabled: reviewMutation.isPending, className: "w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 rounded-xl text-xs font-bold text-white transition-all shadow-xs flex items-center justify-center gap-1.5", children: [reviewMutation.isPending ? _jsx(Loader2, { className: "w-3.5 h-3.5 animate-spin" }) : _jsx(Sparkles, { className: "w-3.5 h-3.5" }), " Compute via Pure Text"] })] }), _jsxs("div", { ...getRootProps(), className: cn("border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all bg-white overflow-hidden group", isDragActive ? "border-indigo-500 bg-indigo-50/40" : "border-slate-200 hover:border-indigo-400", reviewMutation.isPending && "opacity-40 pointer-events-none"), children: [_jsx("input", { ...getInputProps() }), reviewMutation.isPending ? (_jsxs("div", { className: "py-4 flex flex-col items-center justify-center", children: [_jsx(Loader2, { className: "w-8 h-8 text-indigo-600 animate-spin mb-2" }), _jsx("p", { className: "text-xs font-bold text-indigo-950", children: "AI Extraction Layer Syncing..." })] })) : (_jsxs("div", { children: [_jsx("div", { className: "w-10 h-10 bg-slate-50 text-slate-400 rounded-xl flex items-center justify-center mx-auto mb-2 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition-all", children: _jsx(Upload, { className: "w-4 h-4" }) }), _jsx("p", { className: "text-xs font-bold text-slate-700", children: "Drop your document or image scan here" }), _jsxs("div", { className: "mt-3 flex items-center justify-center gap-3 text-[10px] font-bold text-slate-400 border-t border-slate-50 pt-3", children: [_jsxs("span", { className: "flex items-center gap-0.5", children: [_jsx(FileText, { className: "w-3 h-3 text-indigo-400" }), " PDF"] }), _jsxs("span", { className: "flex items-center gap-0.5", children: [_jsx(Image, { className: "w-3 h-3 text-violet-400" }), " IMAGE"] })] })] }))] })] }), _jsx("div", { className: "lg:col-span-2 min-h-[500px] flex flex-col bg-white rounded-2xl border border-slate-100 shadow-xs overflow-hidden", children: !selectedReview ? (_jsxs("div", { className: "flex-1 flex flex-col items-center justify-center text-center p-8 bg-slate-50/20", children: [_jsx(ClipboardCheck, { className: "w-12 h-12 text-slate-200 mb-2" }), _jsx("p", { className: "text-xs font-bold text-slate-400 uppercase tracking-wider", children: "Awaiting Generation Input" })] })) : (_jsxs("div", { className: "p-6 flex-1 flex flex-col justify-between", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50 p-3 rounded-xl border border-slate-100 mb-6", children: [_jsxs("div", { className: "flex items-center gap-1.5 text-xs font-bold text-slate-700", children: [_jsx(Eye, { className: "w-4 h-4 text-indigo-600" }), " Pipeline Conversions"] }), _jsxs("div", { className: "flex items-center gap-2", children: [_jsxs("button", { type: "button", onClick: () => handleRouteConversion("/quotations/new"), className: "flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all shadow-3xs", children: [_jsx(FileSpreadsheet, { className: "w-3.5 h-3.5" }), " Convert to Quote"] }), _jsxs("button", { type: "button", onClick: () => handleRouteConversion("/invoices/new"), className: "flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all shadow-3xs", children: [_jsx(Receipt, { className: "w-3.5 h-3.5" }), " Convert to Invoice"] })] })] }), _jsxs("div", { className: "border border-slate-200/80 rounded-xl p-6 bg-white shadow-3xs space-y-6 flex-1 mb-4", children: [_jsxs("div", { className: "flex justify-between items-start border-b border-slate-100 pb-4", children: [_jsxs("div", { className: "space-y-1", children: [_jsx("h2", { className: "text-sm font-black text-indigo-600 uppercase tracking-wider", children: companyName || "Untitled Organization Entity" }), companyAddress && _jsxs("p", { className: "text-[11px] text-slate-400 font-medium flex items-center gap-0.5", children: [_jsx(MapPin, { className: "w-3 h-3" }), " ", companyAddress, ", ", companyCity] }), locationNumber && _jsxs("p", { className: "text-[11px] text-slate-400 font-mono", children: ["\uD83D\uDCDE ", locationNumber] })] }), _jsx("div", { className: "text-right", children: _jsx("span", { className: "text-[10px] font-black tracking-widest bg-slate-900 text-white px-2 py-0.5 rounded uppercase", children: "AI Draft" }) })] }), _jsxs("div", { className: "bg-slate-50 p-3 rounded-lg border border-slate-100 text-[11px]", children: [_jsx("span", { className: "text-[9px] text-slate-400 uppercase font-black tracking-wider block mb-0.5", children: "Billing Recipient Entity" }), _jsxs("p", { className: "font-bold text-slate-900", children: [salutation, " ", clientName || "Unassigned Corporate Lead"] })] }), _jsxs("div", { className: "space-y-2", children: [_jsx("span", { className: "text-[9px] text-slate-400 uppercase font-black tracking-wider block mb-1", children: "Parsed Ledger Arrays" }), _jsxs("table", { className: "w-full text-left text-xs border-collapse", children: [_jsx("thead", { children: _jsxs("tr", { className: "bg-indigo-50 border-b border-indigo-100 text-indigo-950 font-bold text-[10px]", children: [_jsx("th", { className: "p-2", children: "Item Matrix Task Breakdown" }), _jsx("th", { className: "p-2 text-center w-16", children: "Qty" }), _jsx("th", { className: "p-2 text-right w-24", children: "Price" })] }) }), _jsxs("tbody", { className: "divide-y divide-slate-100 font-medium text-slate-700", children: [selectedReview.extracted_items?.map((item, idx) => (_jsxs("tr", { className: "hover:bg-slate-50/40", children: [_jsx("td", { className: "p-2 truncate max-w-[200px] text-slate-900 font-semibold", children: item.description }), _jsx("td", { className: "p-2 text-center font-mono text-slate-400 text-xs", children: item.quantity }), _jsx("td", { className: "p-2 text-right font-mono text-slate-900", children: item.unit_price?.toLocaleString() })] }, idx))), (!selectedReview.extracted_items || selectedReview.extracted_items.length === 0) && (_jsx("tr", { children: _jsx("td", { colSpan: 3, className: "p-4 text-center text-slate-300 italic", children: "No transactional entries parsed in current document layer." }) }))] })] })] })] })] })) })] })] }));
}
