import { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Save, User, Eye, LayoutGrid, Sparkles, MapPin, Building2 } from "lucide-react";
import { companiesApi, quotationsApi } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const lineItemSchema = z.object({
  description: z.string().min(1, "Description required"),
  quantity: z.coerce.number().min(1),
  unit_price: z.coerce.number().min(0),
  order: z.number().default(0),
});

const quotationSchema = z.object({
  company: z.string().optional(),
  client: z.string().optional(),
  salutation: z.string().default("Mr."),
  client_phone: z.string().min(1, "Phone number required"),
  building_address: z.string().min(1, "Building address required"),
  currency: z.string().default("KES"),
  issue_date: z.string().min(1),
  validity_period: z.string().default("30"),
  due_date: z.string().min(1),
  notes: z.string().optional(),
  terms: z.string().optional(),
  line_items: z.array(lineItemSchema).min(1, "Add at least one item line"),

  // Fixed: Raw manual text override collectors (Bypasses backend persistence mandates)
  raw_client_name: z.string().optional(),
  raw_company_name: z.string().optional(),
  raw_company_address: z.string().optional(),
  raw_company_city: z.string().optional(),
  raw_company_location_number: z.string().optional(),
});

type QuotationFormValues = z.infer<typeof quotationSchema>;

export default function QuotationEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const aiPrefillData = location.state?.prefill;

  const [previewMode, setPreviewMode] = useState<"editor" | "split">("split");

  const [isManualCompany, setIsManualCompany] = useState(false);
  const [isManualClient, setIsManualClient] = useState(false);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data: clientsData } = useQuery({
    queryKey: ["clients", company?.id],
    queryFn: () => companiesApi.clients.list(company?.id),
    enabled: Boolean(company?.id)
  });
  const clients = clientsData?.data?.results ?? [];

  const { data: quoteData } = useQuery({
    queryKey: ["quotation", id],
    queryFn: () => quotationsApi.get(id!),
    enabled: isEditing,
  });

  const { register, control, handleSubmit, watch, reset, setValue } = useForm<QuotationFormValues>({
    resolver: zodResolver(quotationSchema),
    defaultValues: {
      company: company?.id ?? "",
      salutation: "Mr.",
      currency: company?.default_currency ?? "KES",
      issue_date: new Date().toISOString().split("T")[0],
      validity_period: "30",
      due_date: new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
      line_items: [{ description: "", quantity: 1, unit_price: 0, order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });

  const selectedClientId = watch("client");
  const watchedItems = watch("line_items") || [];
  const currencySymbol = watch("currency") || "KES";
  const notesText = watch("notes");
  const termsText = watch("terms");
  const issueDateWatch = watch("issue_date");
  const validityPeriodWatch = watch("validity_period");


  const manualClientName = watch("raw_client_name");
  const manualCompanyName = watch("raw_company_name");
  const manualCompanyAddress = watch("raw_company_address");
  const manualCompanyCity = watch("raw_company_city");
  const manualLocationNumber = watch("raw_company_location_number");

  useEffect(() => {
    if (issueDateWatch && validityPeriodWatch) {
      const baseDate = new Date(issueDateWatch);
      const daysOffset = parseInt(validityPeriodWatch, 10);
      if (!isNaN(daysOffset)) {
        baseDate.setDate(baseDate.getDate() + daysOffset);
        setValue("due_date", baseDate.toISOString().split("T")[0]);
      }
    }
  }, [issueDateWatch, validityPeriodWatch, setValue]);

  useEffect(() => {
    if (selectedClientId && clients.length > 0 && !isManualClient) {
      const match = clients.find(c => c.id === selectedClientId);
      if (match) {
        if (match.phone) setValue("client_phone", match.phone);
        if (match.address) setValue("building_address", match.address);
      }
    }
  }, [selectedClientId, clients, isManualClient, setValue]);

  useEffect(() => {
    if (company && !isEditing) {
      setValue("company", company.id);
      setValue("currency", company.default_currency || "KES");
    }
  }, [company, isEditing, setValue]);

  useEffect(() => {
    if (quoteData?.data) {
      reset(quoteData.data as any);
    }
  }, [quoteData, reset]);

  useEffect(() => {
    if (aiPrefillData && !isEditing) {
      if (aiPrefillData.extracted_company_name) {
        setIsManualCompany(true);
        setValue("raw_company_name", aiPrefillData.extracted_company_name);
      }
      if (aiPrefillData.extracted_company_address) setValue("raw_company_address", aiPrefillData.extracted_company_address);
      if (aiPrefillData.extracted_company_city) setValue("raw_company_city", aiPrefillData.extracted_company_city);
      if (aiPrefillData.extracted_company_location_number) setValue("raw_company_location_number", aiPrefillData.extracted_company_location_number);
      if (aiPrefillData.extracted_salutation) setValue("salutation", aiPrefillData.extracted_salutation);

      if (aiPrefillData.extracted_client_name) {
        setIsManualClient(true);
        setValue("raw_client_name", aiPrefillData.extracted_client_name);
      }

      if (aiPrefillData.extracted_currency) {
        setValue("currency", aiPrefillData.extracted_currency);
      }

      if (Array.isArray(aiPrefillData.extracted_items) && aiPrefillData.extracted_items.length > 0) {
        setValue("line_items", aiPrefillData.extracted_items.map((item: any, idx: number) => ({
          description: item.description || "Parsed Estimate Item",
          quantity: Number(item.quantity) || 1,
          unit_price: Number(item.unit_price) || 0,
          order: idx
        })));
      }
    }
  }, [aiPrefillData, isEditing, setValue]);

  const totalAmount = watchedItems.reduce((sum, item) => sum + ((item?.quantity || 0) * (item?.unit_price || 0)), 0);

  const saveMutation = useMutation({
    mutationFn: (values: QuotationFormValues) => {
      const payload = {
        ...values,
        company: isManualCompany ? null : values.company,
        client: isManualClient ? null : values.client,
        subtotal: String(totalAmount.toFixed(2)),
        tax_amount: "0.00",
        total_amount: String(totalAmount.toFixed(2)),
      };
      return quotationsApi.create(payload as any);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotations"] });
      navigate("/quotations");
    }
  });

  return (
    <div className="p-4 sm:p-6 max-w-[1700px] mx-auto bg-gray-50/30 min-h-screen font-sans text-slate-800">

      {/* Title block */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 bg-white p-4 rounded-2xl border border-gray-100 shadow-xs">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => navigate("/quotations")} className="p-2 hover:bg-gray-50 text-gray-500 rounded-xl transition-all">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
              {isEditing ? "Edit Quotation" : "Create Proposal Estimate"}
              {aiPrefillData && <span className="text-[10px] bg-amber-50 text-amber-800 font-bold uppercase tracking-wider px-2 py-0.5 border border-amber-200 rounded-md flex items-center gap-0.5"><Sparkles className="w-3 h-3 text-amber-500" /> AI Populated</span>}
            </h1>
            <p className="text-gray-400 text-xs">Direct flat rate structural engine baseline.</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center bg-gray-100 p-0.5 rounded-xl border border-gray-200/40">
            <button type="button" onClick={() => setPreviewMode("editor")} className={cn("flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all", previewMode === "editor" ? "bg-white text-gray-900 shadow-xs" : "text-gray-400 hover:text-gray-700")}>
              <LayoutGrid className="w-3.5 h-3.5" /> Core Form
            </button>
            <button type="button" onClick={() => setPreviewMode("split")} className={cn("flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all", previewMode === "split" ? "bg-white text-gray-900 shadow-xs" : "text-gray-400 hover:text-gray-700")}>
              <Eye className="w-3.5 h-3.5" /> Split Preview
            </button>
          </div>
        </div>
      </div>

      <div className={cn("grid grid-cols-1 gap-6 transition-all duration-300", previewMode === "split" ? "xl:grid-cols-2" : "max-w-4xl mx-auto")}>

        {/* INPUT FORM BLOCK */}
        <form onSubmit={handleSubmit((data) => saveMutation.mutate(data))} className="space-y-6">

          {/* Issuing company control override block panel */}
          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <h3 className="font-bold text-slate-800 text-xs sm:text-sm flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-600" /> Quotation Provider Identity
              </h3>
              <button type="button" onClick={() => setIsManualCompany(!isManualCompany)} className="text-[11px] font-bold text-indigo-600 hover:underline bg-indigo-50 px-2 py-1 rounded">
                {isManualCompany ? "Use Saved Database Profile" : "Type Dynamic Company Info (No Save)"}
              </button>
            </div>

            {isManualCompany ? (
              <div className="space-y-3 animate-fade-in">
                <div>
                  <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Company Name Override</label>
                  <input type="text" {...register("raw_company_name")} placeholder="e.g. Acme Tech Solutions" className="w-full text-xs border border-gray-200 rounded-xl p-2.5 focus:border-indigo-500 bg-white" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" {...register("raw_company_address")} placeholder="Street / Building Address" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
                  <input type="text" {...register("raw_company_city")} placeholder="City" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
                </div>
                <input type="text" {...register("raw_company_location_number")} placeholder="Location / Contact Phone Number" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
              </div>
            ) : (
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Select Active Company Profile</label>
                <select {...register("company")} className="w-full border border-gray-200 rounded-xl p-2.5 text-xs bg-white">
                  <option value={company?.id}>{company?.name || "System Core Corporate Profile"}</option>
                </select>
              </div>
            )}
          </div>

          {/* Client Target Assignee Field Override block */}
          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <h3 className="font-bold text-slate-800 text-xs sm:text-sm flex items-center gap-2">
                <User className="w-4 h-4 text-violet-600" /> Target Assignee
              </h3>
              <button type="button" onClick={() => setIsManualClient(!isManualClient)} className="text-[11px] font-bold text-violet-600 hover:underline bg-violet-50 px-2 py-1 rounded">
                {isManualClient ? "Pick Saved Profile" : "Type Custom Customer Directly"}
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Prefix</label>
                <select {...register("salutation")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                  {["Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Messrs."].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              <div className="sm:col-span-2">
                {isManualClient ? (
                  <div className="animate-fade-in">
                    <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">One-Off Unsaved Customer Name</label>
                    <input type="text" {...register("raw_client_name")} placeholder="Type custom representative name..." className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
                  </div>
                ) : (
                  <div>
                    <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Select Client Account</label>
                    <select {...register("client")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                      <option value="">Choose a customer profile...</option>
                      {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Contact Phone</label>
                <input type="text" {...register("client_phone")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Corporate/Building Address</label>
                <input type="text" {...register("building_address")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Currency Code</label>
                <select {...register("currency")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                  {["KES", "USD", "EUR", "GBP"].map(curr => <option key={curr} value={curr}>{curr}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Issue Date</label>
                <input type="date" {...register("issue_date")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Validity Period</label>
                <select {...register("validity_period")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                  <option value="7">7 Days Validity</option>
                  <option value="15">15 Days Validity</option>
                  <option value="30">30 Days Validity</option>
                  <option value="60">60 Days Validity</option>
                </select>
              </div>
            </div>
          </div>

          {/* Pricing Items Matrices distribution rows configuration section */}
          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs">
            <h3 className="font-bold text-slate-800 text-xs sm:text-sm mb-3">Line Pricing Items</h3>
            <div className="space-y-3">
              {fields.map((field, index) => (
                <div key={field.id} className="flex flex-col sm:flex-row items-center gap-3 bg-slate-50/50 p-3 rounded-xl border border-gray-100">
                  <input {...register(`line_items.${index}.description` as const)} placeholder="Item description breakdown..." className="w-full border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm bg-white" />
                  <input type="number" {...register(`line_items.${index}.quantity` as const)} placeholder="Qty" className="w-full sm:w-20 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center bg-white" />
                  <input type="number" step="0.01" {...register(`line_items.${index}.unit_price` as const)} placeholder="Price" className="w-full sm:w-32 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-right bg-white" />
                  {fields.length > 1 && (
                    <button type="button" onClick={() => remove(index)} className="p-1.5 text-gray-400 hover:text-rose-500 transition-colors"><Trash2 className="w-4 h-4" /></button>
                  )}
                </div>
              ))}
            </div>
            <button type="button" onClick={() => append({ description: "", quantity: 1, unit_price: 0, order: fields.length })} className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors">
              <Plus className="w-3.5 h-3.5" /> Add Row
            </button>
          </div>

          <div className="bg-slate-900 rounded-2xl p-5 text-white flex justify-between items-center shadow-md">
            <div>
              <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wide">Combined Total Summary</p>
              <h2 className="text-2xl font-black text-indigo-400">{currencySymbol} {totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</h2>
            </div>
            <button type="submit" disabled={saveMutation.isPending} className="bg-indigo-600 hover:bg-indigo-500 font-bold text-xs text-white px-6 py-3.5 rounded-xl flex items-center gap-1.5">
              <Save className="w-4 h-4" /> Save Proposal
            </button>
          </div>
        </form>

        {/* RE-RENDER SPLIT LIVE PREVIEW BLOCK CANVAS */}
        {previewMode === "split" && (
          <div className="hidden xl:block sticky top-6 self-start bg-white rounded-3xl border border-gray-200 p-8 shadow-md text-xs text-slate-700 min-h-[700px] flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-start border-b border-gray-100 pb-6 mb-6">
                <div className="space-y-2.5">
                  <div className="w-12 h-12 bg-indigo-600 text-white rounded-xl flex items-center justify-center font-black text-sm">
                    {(manualCompanyName || company?.name || "D")[0]}
                  </div>
                  <div>
                    <h4 className="font-bold text-slate-900 text-sm">{manualCompanyName || company?.name || "DocFlow Provider"}</h4>
                    <p className="text-gray-400 text-[11px] font-medium flex items-center gap-0.5">
                      <MapPin className="w-3 h-3 text-slate-300" /> {manualCompanyAddress || company?.address_line1 || "Nairobi, Kenya"} {manualCompanyCity && `, ${manualCompanyCity}`}
                    </p>
                    {manualLocationNumber && <p className="text-[10px] text-slate-400 font-mono">📞 {manualLocationNumber}</p>}
                  </div>
                </div>
                <div className="text-right">
                  <h2 className="text-xl font-black text-indigo-600 uppercase tracking-tight">ESTIMATE STATEMENT</h2>
                  <p className="font-mono text-gray-400 font-bold text-sm">QT-{new Date().getFullYear()}-DYNAMIC</p>
                </div>
              </div>

              <div className="bg-slate-50 p-4 rounded-xl border border-gray-100 mb-6">
                <p className="text-[9px] font-bold text-gray-400 uppercase tracking-wide">Quotation Target Representative</p>
                <p className="text-sm font-bold text-slate-900 mt-1">
                  {watch("salutation")} {isManualClient ? (manualClientName || <span className="text-slate-300 italic">Untitled Custom Buyer</span>) : (clients.find(c => c.id === selectedClientId)?.name || <span className="text-slate-300 italic">Unassigned Account</span>)}
                </p>
              </div>

              <table className="w-full text-left border-collapse mb-6">
                <thead>
                  <tr className="bg-slate-900 text-white text-[9px] uppercase font-bold tracking-wider">
                    <th className="p-2.5 rounded-tl-lg w-3/5">Task Description</th>
                    <th className="p-2.5 text-center w-1/5">Qty</th>
                    <th className="p-2.5 text-right rounded-tr-lg w-1/5">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 font-medium">
                  {watchedItems.map((item, i) => (
                    <tr key={i} className="text-slate-800 text-[11px]">
                      <td className="p-2.5 text-slate-600 truncate max-w-[250px] font-semibold">{item.description || <span className="text-gray-300 italic">Untitled Task Item</span>}</td>
                      <td className="p-2.5 text-center font-mono text-gray-400">{item.quantity || 0}</td>
                      <td className="p-2.5 text-right text-slate-900 font-bold">{formatCurrency((item.quantity || 0) * (item.unit_price || 0), currencySymbol)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end border-t border-gray-100 pt-4">
              <div className="w-52 text-right bg-slate-50 p-2 rounded-lg text-sm font-black text-slate-900 flex justify-between">
                <span>Total Budgeted Value</span>
                <span className="text-indigo-600">{formatCurrency(totalAmount, currencySymbol)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}