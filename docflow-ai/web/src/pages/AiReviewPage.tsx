import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { useNavigate } from "react-router-dom";
import {
  Sparkles, Upload, FileText, Image, Loader2, History, Layers, ClipboardCheck,
  Terminal, FileDown, Eye, RefreshCw, FileSpreadsheet, Receipt, Building, User, Phone, MapPin
} from "lucide-react";
import { aiApi, companiesApi } from "@/lib/api";
import { formatDate, cn } from "@/lib/utils";

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
  const [selectedReview, setSelectedReview] = useState<any | null>(null);
  const [exportFormat, setExportFormat] = useState<"pdf" | "docx">("pdf");
  const [isExporting, setIsExporting] = useState(false);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data: reviewsData, isLoading: loadingHistory } = useQuery({
    queryKey: ["ai-reviews", company?.id],
    queryFn: () => aiApi.listReviews(company?.id),
    enabled: Boolean(company?.id),
  });
  const reviews = reviewsData ?? [];

  const updateFormState = (data: any) => {
    if (data.extracted_company_name) setCompanyName(data.extracted_company_name);
    if (data.extracted_company_address) setCompanyAddress(data.extracted_company_address);
    if (data.extracted_company_city) setCompanyCity(data.extracted_company_city);
    if (data.extracted_company_location_number) setLocationNumber(data.extracted_company_location_number);
    if (data.extracted_salutation) setSalutation(data.extracted_salutation);
    if (data.extracted_client_name) setClientName(data.extracted_client_name);
  };

  const reviewMutation = useMutation({
    mutationFn: (file?: File) => {
      const fd = new FormData();
      if (file) fd.append("file", file);

      // Inject manual context instructions for smart data creation overrides
      const directiveSummary = `
        ${aiInstructions}. 
        Explicit context setup: Company Name: ${companyName}, Address: ${companyAddress}, City: ${companyCity}, Phone/Location number: ${locationNumber}, Client Prefix: ${salutation}, Client Target Name: ${clientName}
      `;
      fd.append("instructions", directiveSummary.trim());
      if (company?.id) fd.append("company", company.id);

      return aiApi.reviewContract(fd);
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["ai-reviews"] });
      setSelectedReview(res.data);
      updateFormState(res.data);
    },
    onError: (err: any) => {
      alert(`AI Execution Error: ${err.response?.data?.detail || "Failed to analyze layout configuration metrics."}`);
    }
  });

  const onDrop = useCallback((files: File[]) => {
    if (files[0] && company) reviewMutation.mutate(files[0]);
  }, [company, reviewMutation]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg", ".jpeg", ".webp"] },
    maxFiles: 1,
  });

  const handleRouteConversion = (targetRoute: "/quotations/new" | "/invoices/new") => {
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

  return (
    <div className="p-4 sm:p-8 bg-slate-50/60 min-h-screen flex flex-col font-sans text-slate-800 antialiased">

      {/* Brand Header */}
      <div className="mb-6 bg-white p-6 rounded-2xl border border-slate-100 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-950 flex items-center gap-2">
            <div className="p-2 bg-indigo-600 rounded-xl text-white shadow-xs">
              <Sparkles className="w-5 h-5 fill-indigo-200" />
            </div>
            Smart Automated Document Workspace
          </h1>
          <p className="text-slate-400 text-xs sm:text-sm mt-0.5">Drop invoice image logs or supply parameters manually below to experience instant AI synthesis.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 items-start">

        {/* Left Control Parameters Setup Column */}
        <div className="space-y-6 lg:col-span-1">

          {/* Quick Identity Input Card */}
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-4">
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5"><Building className="w-3.5 h-3.5 text-indigo-500" /> Company Parameters</h3>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1">Company Name</label>
                <input type="text" value={companyName} onChange={e => setCompanyName(e.target.value)} placeholder="e.g. DocFlow Global Ltd" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none focus:border-indigo-500 bg-slate-50/50" />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1">Street Address</label>
                  <input type="text" value={companyAddress} onChange={e => setCompanyAddress(e.target.value)} placeholder="Mombasa Road" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1">City</label>
                  <input type="text" value={companyCity} onChange={e => setCompanyCity(e.target.value)} placeholder="Nairobi" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wide block mb-1 flex items-center gap-0.5"><Phone className="w-2.5 h-2.5" /> Contact Location Number</label>
                <input type="text" value={locationNumber} onChange={e => setLocationNumber(e.target.value)} placeholder="e.g. +254 700 000 000" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" />
              </div>
            </div>

            <div className="border-t border-slate-100 pt-4 space-y-3">
              <h3 className="font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5"><User className="w-3.5 h-3.5 text-violet-500" /> Target Assignee</h3>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prefix</label>
                  <select value={salutation} onChange={e => setSalutation(e.target.value)} className="w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white focus:outline-none">
                    {["Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Messrs."].map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div className="col-span-2">
                  <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Client Name</label>
                  <input type="text" value={clientName} onChange={e => setClientName(e.target.value)} placeholder="John Doe Enterprise" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:outline-none bg-slate-50/50" />
                </div>
              </div>
            </div>
          </div>

          {/* Prompt Instructions Terminal Box Area */}
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-3">
            <h3 className="font-bold text-xs uppercase tracking-wider text-slate-400 flex items-center gap-1.5"><Terminal className="w-3.5 h-3.5 text-emerald-500" /> Natural Language Directives</h3>
            <textarea
              value={aiInstructions}
              onChange={(e) => setAiInstructions(e.target.value)}
              rows={3}
              placeholder="Type your instruction or budget criteria here (e.g. 'Write a quotation for 5 laptop replacement screens with 16% tax rate...')"
              className="w-full border border-slate-200 rounded-xl p-3 text-xs focus:outline-none focus:border-indigo-500 bg-slate-50/50 resize-none font-medium text-slate-700"
            />
            <button
              type="button"
              onClick={() => reviewMutation.mutate()}
              disabled={reviewMutation.isPending}
              className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 rounded-xl text-xs font-bold text-white transition-all shadow-xs flex items-center justify-center gap-1.5"
            >
              {reviewMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />} Compute via Pure Text
            </button>
          </div>

          {/* Interactive Drag & Drop Box */}
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all bg-white overflow-hidden group",
              isDragActive ? "border-indigo-500 bg-indigo-50/40" : "border-slate-200 hover:border-indigo-400",
              reviewMutation.isPending && "opacity-40 pointer-events-none"
            )}
          >
            <input {...getInputProps()} />
            {reviewMutation.isPending ? (
              <div className="py-4 flex flex-col items-center justify-center">
                <Loader2 className="w-8 h-8 text-indigo-600 animate-spin mb-2" />
                <p className="text-xs font-bold text-indigo-950">AI Extraction Layer Syncing...</p>
              </div>
            ) : (
              <div>
                <div className="w-10 h-10 bg-slate-50 text-slate-400 rounded-xl flex items-center justify-center mx-auto mb-2 group-hover:bg-indigo-50 group-hover:text-indigo-600 transition-all">
                  <Upload className="w-4 h-4" />
                </div>
                <p className="text-xs font-bold text-slate-700">Drop your document or image scan here</p>
                <div className="mt-3 flex items-center justify-center gap-3 text-[10px] font-bold text-slate-400 border-t border-slate-50 pt-3">
                  <span className="flex items-center gap-0.5"><FileText className="w-3 h-3 text-indigo-400" /> PDF</span>
                  <span className="flex items-center gap-0.5"><Image className="w-3 h-3 text-violet-400" /> IMAGE</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Output Document Sheet Preview Column */}
        <div className="lg:col-span-2 min-h-[500px] flex flex-col bg-white rounded-2xl border border-slate-100 shadow-xs overflow-hidden">
          {!selectedReview ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center p-8 bg-slate-50/20">
              <ClipboardCheck className="w-12 h-12 text-slate-200 mb-2" />
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Awaiting Generation Input</p>
            </div>
          ) : (
            <div className="p-6 flex-1 flex flex-col justify-between">

              {/* Document Conversion Header Ribbon Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-50 p-3 rounded-xl border border-slate-100 mb-6">
                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700"><Eye className="w-4 h-4 text-indigo-600" /> Pipeline Conversions</div>
                <div className="flex items-center gap-2">
                  <button type="button" onClick={() => handleRouteConversion("/quotations/new")} className="flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all shadow-3xs">
                    <FileSpreadsheet className="w-3.5 h-3.5" /> Convert to Quote
                  </button>
                  <button type="button" onClick={() => handleRouteConversion("/invoices/new")} className="flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all shadow-3xs">
                    <Receipt className="w-3.5 h-3.5" /> Convert to Invoice
                  </button>
                </div>
              </div>

              {/* Live Render Template Block Canvas */}
              <div className="border border-slate-200/80 rounded-xl p-6 bg-white shadow-3xs space-y-6 flex-1 mb-4">
                <div className="flex justify-between items-start border-b border-slate-100 pb-4">
                  <div className="space-y-1">
                    <h2 className="text-sm font-black text-indigo-600 uppercase tracking-wider">{companyName || "Untitled Organization Entity"}</h2>
                    {companyAddress && <p className="text-[11px] text-slate-400 font-medium flex items-center gap-0.5"><MapPin className="w-3 h-3" /> {companyAddress}, {companyCity}</p>}
                    {locationNumber && <p className="text-[11px] text-slate-400 font-mono">📞 {locationNumber}</p>}
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] font-black tracking-widest bg-slate-900 text-white px-2 py-0.5 rounded uppercase">AI Draft</span>
                  </div>
                </div>

                <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 text-[11px]">
                  <span className="text-[9px] text-slate-400 uppercase font-black tracking-wider block mb-0.5">Billing Recipient Entity</span>
                  <p className="font-bold text-slate-900">{salutation} {clientName || "Unassigned Corporate Lead"}</p>
                </div>

                {/* Items Distribution Line Block Grid */}
                <div className="space-y-2">
                  <span className="text-[9px] text-slate-400 uppercase font-black tracking-wider block mb-1">Parsed Ledger Arrays</span>
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-indigo-50 border-b border-indigo-100 text-indigo-950 font-bold text-[10px]">
                        <th className="p-2">Item Matrix Task Breakdown</th>
                        <th className="p-2 text-center w-16">Qty</th>
                        <th className="p-2 text-right w-24">Price</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium text-slate-700">
                      {selectedReview.extracted_items?.map((item: any, idx: number) => (
                        <tr key={idx} className="hover:bg-slate-50/40">
                          <td className="p-2 truncate max-w-[200px] text-slate-900 font-semibold">{item.description}</td>
                          <td className="p-2 text-center font-mono text-slate-400 text-xs">{item.quantity}</td>
                          <td className="p-2 text-right font-mono text-slate-900">{item.unit_price?.toLocaleString()}</td>
                        </tr>
                      ))}
                      {(!selectedReview.extracted_items || selectedReview.extracted_items.length === 0) && (
                        <tr><td colSpan={3} className="p-4 text-center text-slate-300 italic">No transactional entries parsed in current document layer.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

            </div>
          )}
        </div>

      </div>
    </div>
  );
}