import { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Save, FileDown, Eye, LayoutGrid, Building2, Calendar, Sparkles, MapPin, UserCheck } from "lucide-react";
import { companiesApi, invoicesApi } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const lineItemSchema = z.object({
  description: z.string().min(1, "Description required"),
  quantity: z.coerce.number().min(1),
  unit_price: z.coerce.number().min(0),
  order: z.number().default(0),
});

const invoiceSchema = z.object({
  company: z.string().optional(),
  client: z.string().optional(),
  currency: z.string().default("KES"),
  issue_date: z.string().min(1),
  due_date: z.string().min(1),
  notes: z.string().optional(),
  terms: z.string().optional(),
  tax_rate: z.coerce.number().default(16),
  discount_amount: z.coerce.number().default(0),
  line_items: z.array(lineItemSchema).min(1, "Include at least one item line"),

  // Custom form override collectors
  raw_client_name: z.string().optional(),
  raw_company_name: z.string().optional(),
  raw_company_address: z.string().optional(),
  raw_company_city: z.string().optional(),
  raw_company_location_number: z.string().optional(),
});

type InvoiceFormValues = z.infer<typeof invoiceSchema>;

export default function InvoiceEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const aiPrefillData = location.state?.prefill;

  const [viewMode, setViewMode] = useState<"editor" | "split">("split");
  const [exportType, setExportType] = useState<"pdf" | "docx">("pdf");

  // Mode status controllers for unpersisted data creation states
  const [isManualClient, setIsManualClient] = useState(false);
  const [isManualCompany, setIsManualCompany] = useState(false);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data: clientsData } = useQuery({
    queryKey: ["clients", company?.id],
    queryFn: () => companiesApi.clients.list(company?.id),
    enabled: Boolean(company?.id)
  });
  const clients = clientsData?.data?.results ?? [];

  const { register, control, handleSubmit, watch, reset, setValue } = useForm<InvoiceFormValues>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {
      company: company?.id ?? "",
      currency: "KES",
      issue_date: new Date().toISOString().split("T")[0],
      due_date: new Date(Date.now() + 14 * 86400000).toISOString().split("T")[0],
      tax_rate: 16,
      discount_amount: 0,
      line_items: [{ description: "", quantity: 1, unit_price: 0, order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });

  const targetClientId = watch("client");
  const currencyToken = watch("currency") || "KES";
  const taxRatePercent = watch("tax_rate") || 0;
  const discountDeduction = watch("discount_amount") || 0;
  const watchedLineItems = watch("line_items") || [];
  const noteContent = watch("notes");

  // Dynamic state readers for preview panel syncing
  const manualClientName = watch("raw_client_name");
  const manualCompanyName = watch("raw_company_name");
  const manualCompanyAddress = watch("raw_company_address");
  const manualCompanyCity = watch("raw_company_city");
  const manualLocationNumber = watch("raw_company_location_number");

  useEffect(() => {
    if (company && !isEditing) {
      setValue("company", company.id);
      setValue("currency", company.default_currency || "KES");
    }
  }, [company, isEditing, setValue]);

  useEffect(() => {
    if (aiPrefillData && !isEditing) {
      if (aiPrefillData.extracted_company_name) {
        setIsManualCompany(true);
        setValue("raw_company_name", aiPrefillData.extracted_company_name);
      }
      if (aiPrefillData.extracted_company_address) setValue("raw_company_address", aiPrefillData.extracted_company_address);
      if (aiPrefillData.extracted_company_city) setValue("raw_company_city", aiPrefillData.extracted_company_city);
      if (aiPrefillData.extracted_company_location_number) setValue("raw_company_location_number", aiPrefillData.extracted_company_location_number);

      if (aiPrefillData.extracted_client_name) {
        setIsManualClient(true);
        setValue("raw_client_name", aiPrefillData.extracted_client_name);
      }
      if (aiPrefillData.extracted_currency) setValue("currency", aiPrefillData.extracted_currency);

      if (Array.isArray(aiPrefillData.extracted_items) && aiPrefillData.extracted_items.length > 0) {
        setValue("line_items", aiPrefillData.extracted_items.map((item: any, idx: number) => ({
          description: item.description || "Extracted Item",
          quantity: Number(item.quantity) || 1,
          unit_price: Number(item.unit_price) || 0,
          order: idx
        })));
      }
    }
  }, [aiPrefillData, isEditing, setValue]);

  const subtotalAmount = watchedLineItems.reduce((acc, row) => acc + ((row?.quantity || 0) * (row?.unit_price || 0)), 0);
  const calculatedTax = subtotalAmount * (taxRatePercent / 100);
  const grandTotal = subtotalAmount + calculatedTax - discountDeduction;

  const saveMutation = useMutation({
    mutationFn: (values: InvoiceFormValues) => {
      const payload = {
        ...values,
        company: isManualCompany ? null : values.company,
        client: isManualClient ? null : values.client,
        subtotal: String(subtotalAmount),
        tax_amount: String(calculatedTax),
        total_amount: String(grandTotal),
      };
      return invoicesApi.create(payload as any);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      navigate("/invoices");
    },
  });

  return (
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto bg-slate-50/40 min-h-screen font-sans text-slate-800">

      {/* Controls panel header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 bg-white p-4 rounded-2xl border border-slate-100 shadow-xs print:hidden">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => navigate("/invoices")} className="p-2 hover:bg-slate-50 text-slate-500 rounded-xl border border-slate-100"><ArrowLeft className="w-4 h-4" /></button>
          <div>
            <h1 className="text-lg font-bold flex items-center gap-1.5">Invoice Ledger Console</h1>
            <p className="text-slate-400 text-xs">Dynamic configurations workspace.</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setViewMode("editor")} className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all", viewMode === "editor" ? "bg-slate-900 text-white shadow-xs" : "text-slate-400 hover:text-slate-600")}><LayoutGrid className="w-3.5 h-3.5 inline mr-1" /> Form View</button>
          <button type="button" onClick={() => setViewMode("split")} className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all", viewMode === "split" ? "bg-slate-900 text-white shadow-xs" : "text-slate-400 hover:text-slate-600")}><Eye className="w-3.5 h-3.5 inline mr-1" /> Interactive View</button>
        </div>
      </div>

      <div className={cn("grid grid-cols-1 gap-6", viewMode === "split" ? "xl:grid-cols-2" : "max-w-4xl mx-auto")}>

        {/* FORM INPUT COLUMN */}
        <form onSubmit={handleSubmit((data) => saveMutation.mutate(data))} className="space-y-5 print:hidden">

          {/* Company Profiles selection cards layout blocks */}
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-50">
              <h3 className="font-bold text-xs sm:text-sm flex items-center gap-2"><Building2 className="w-4 h-4 text-indigo-600" /> Issuing Organization</h3>
              <button type="button" onClick={() => setIsManualCompany(!isManualCompany)} className="text-[11px] font-bold text-indigo-600 hover:underline bg-indigo-50 px-2 py-1 rounded">
                {isManualCompany ? "Choose Saved Profile" : "Type New Company Name Directly"}
              </button>
            </div>

            {isManualCompany ? (
              <div className="space-y-3 animate-fade-in">
                <div>
                  <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Company Name Override</label>
                  <input type="text" {...register("raw_company_name")} placeholder="Type any corporate seller descriptor..." className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:border-indigo-500" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" {...register("raw_company_address")} placeholder="Street Address" className="w-full text-xs border border-slate-200 rounded-xl p-2.5" />
                  <input type="text" {...register("raw_company_city")} placeholder="City Location" className="w-full text-xs border border-slate-200 rounded-xl p-2.5" />
                </div>
                <input type="text" {...register("raw_company_location_number")} placeholder="Contact Mobile / Registration Number" className="w-full text-xs border border-slate-200 rounded-xl p-2.5" />
              </div>
            ) : (
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Profile Base</label>
                <select {...register("company")} className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white">
                  <option value={company?.id}>{company?.name || "DocFlow Base System Account"}</option>
                </select>
              </div>
            )}
          </div>

          {/* Client target profiles selections layout mapping block */}
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-slate-50">
              <h3 className="font-bold text-xs sm:text-sm flex items-center gap-2"><UserCheck className="w-4 h-4 text-violet-600" /> Billing Assignee Target</h3>
              <button type="button" onClick={() => setIsManualClient(!isManualClient)} className="text-[11px] font-bold text-violet-600 hover:underline bg-violet-50 px-2 py-1 rounded">
                {isManualClient ? "Choose Existing Client" : "Type Custom Client Name (No Save)"}
              </button>
            </div>

            {isManualClient ? (
              <div className="animate-fade-in">
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Custom Client Description Name</label>
                <input type="text" {...register("raw_client_name")} placeholder="e.g. Acme International Corporation Ltd" className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:border-indigo-500" />
              </div>
            ) : (
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Select Active Client Profile</label>
                <select {...register("client")} className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white">
                  <option value="">Choose your targeted billing customer index...</option>
                  {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Currency</label>
                <select {...register("currency")} className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white">
                  {["KES", "USD", "EUR", "GBP"].map(curr => <option key={curr} value={curr}>{curr}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Tax Variable (%)</label>
                <input type="number" {...register("tax_rate")} className="w-full border border-slate-200 rounded-xl p-2 text-xs bg-white" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1"><Calendar className="w-3 h-3 inline mr-1" /> Issued Date</label>
                <input type="date" {...register("issue_date")} className="w-full border border-slate-200 rounded-xl p-2 text-xs" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1"><Calendar className="w-3 h-3 inline mr-1" /> Due Date</label>
                <input type="date" {...register("due_date")} className="w-full border border-slate-200 rounded-xl p-2 text-xs" />
              </div>
            </div>
          </div>

          {/* Dynamic Billing Ledger Line Entries Items Distributor Block */}
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs">
            <h3 className="font-bold text-slate-900 text-xs sm:text-sm mb-3">Line Pricing Breakdown Matrix</h3>
            <div className="space-y-3">
              {fields.map((field, index) => (
                <div key={field.id} className="flex flex-col sm:flex-row items-center gap-3 bg-slate-50/60 p-3 rounded-xl border border-slate-100/60">
                  <input {...register(`line_items.${index}.description` as const)} placeholder="Description of billable service..." className="w-full sm:flex-1 border border-slate-200 rounded-lg p-2 text-xs outline-none bg-white" />
                  <input type="number" {...register(`line_items.${index}.quantity` as const)} placeholder="Qty" className="w-full sm:w-16 border border-slate-200 rounded-lg p-2 text-xs text-center" />
                  <input type="number" step="0.01" {...register(`line_items.${index}.unit_price` as const)} placeholder="Price" className="w-full sm:w-24 border border-slate-200 rounded-lg p-2 text-xs text-right" />
                  {fields.length > 1 && (
                    <button type="button" onClick={() => remove(index)} className="p-1 text-slate-400 hover:text-rose-500"><Trash2 className="w-4 h-4" /></button>
                  )}
                </div>
              ))}
            </div>
            <button type="button" onClick={() => append({ description: "", quantity: 1, unit_price: 0, order: fields.length })} className="mt-3 text-xs font-bold text-indigo-600 bg-indigo-50 px-3 py-1.5 rounded-lg inline-flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Append Item Row</button>
          </div>

          {/* Core submit variables action bar panel wrapper block element footer */}
          <div className="bg-slate-950 rounded-2xl p-5 text-white flex justify-between items-center shadow-md">
            <div>
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wide">Balance Valuation</span>
              <h2 className="text-xl font-black text-indigo-400">{currencyToken} {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}</h2>
            </div>
            <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-5 py-2.5 rounded-xl flex items-center gap-1.5"><Save className="w-4 h-4" /> Finalize Invoice Document</button>
          </div>

        </form>

        {/* PIXEL-PERFECT RENDER PREVIEW WRAPPER */}
        {viewMode === "split" && (
          <div className="bg-white rounded-3xl border border-slate-100 p-6 sm:p-12 shadow-sm text-xs text-slate-700 min-h-[660px] flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start border-b border-slate-100 pb-5 mb-5">
                <div className="space-y-2">
                  <div className="w-10 h-10 bg-slate-950 text-white rounded-xl flex items-center justify-center font-black text-xs">
                    {(manualCompanyName || company?.name || "D")[0]}
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-900 text-sm">{manualCompanyName || company?.name || "DocFlow Provider Systems"}</h4>
                    <p className="text-slate-400 text-[11px] font-medium flex items-center gap-0.5">
                      <MapPin className="w-3 h-3 text-slate-300" /> {manualCompanyAddress || company?.address_line1 || "Nairobi, Kenya"} {manualCompanyCity && `, ${manualCompanyCity}`}
                    </p>
                    {manualLocationNumber && <p className="text-[10px] font-mono text-slate-400">📞 {manualLocationNumber}</p>}
                  </div>
                </div>
                <div className="text-right">
                  <h2 className="text-sm font-black text-indigo-600 uppercase tracking-widest">INVOICE STATEMENT</h2>
                  <p className="font-mono text-[11px] font-bold text-slate-900 mt-1">INV-2026-PREVIEW</p>
                </div>
              </div>

              <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 mb-6">
                <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block mb-0.5">Billed Assignee Target</span>
                <h3 className="text-xs font-bold text-slate-900">
                  {isManualClient ? (manualClientName || <span className="text-slate-300 italic">Untitled Custom Client</span>) : (clients.find(c => c.id === targetClientId)?.name || <span className="text-slate-300 italic">No Database Record Assigned</span>)}
                </h3>
              </div>

              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-900 text-white text-[9px] font-bold uppercase">
                    <th className="p-2.5 rounded-l-lg">Task / Item Matrix Specification</th>
                    <th className="p-2.5 text-center w-16">Qty</th>
                    <th className="p-2.5 text-right rounded-r-lg w-24">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50 font-medium text-slate-800">
                  {watchedLineItems.map((row, i) => (
                    <tr key={i}>
                      <td className="p-2.5 truncate max-w-[200px] text-slate-600">{row.description || <span className="text-slate-300 italic">Untitled billable line descriptor</span>}</td>
                      <td className="p-2.5 text-center font-mono text-slate-400">{row.quantity || 0}</td>
                      <td className="p-2.5 text-right font-bold text-slate-900">{formatCurrency((row.quantity || 0) * (row.unit_price || 0), currencyToken)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="border-t border-slate-50 pt-4 flex justify-end">
              <div className="w-56 font-bold text-[11px] text-right space-y-1">
                <div className="flex justify-between text-slate-400"><span>Ledger Subtotal</span><span className="text-slate-900">{formatCurrency(subtotalAmount, currencyToken)}</span></div>
                <div className="flex justify-between text-slate-400"><span>VAT ({taxRatePercent}%)</span><span className="text-slate-900">{formatCurrency(calculatedTax, currencyToken)}</span></div>
                <div className="flex justify-between text-xs font-black text-slate-900 border-t border-slate-100 pt-2 mt-1"><span>Total Valuation</span><span className="text-indigo-600">{formatCurrency(grandTotal, currencyToken)}</span></div>
              </div>
            </div>

          </div>
        )}

      </div>
    </div>
  );
}