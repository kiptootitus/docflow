import { useState, useEffect, useRef } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Save, User, Eye, LayoutGrid, Sparkles, MapPin, Building2, Palette, Image as ImageIcon } from "lucide-react";
import { companiesApi, quotationsApi } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const lineItemSchema = z.object({
  item_type: z.enum(["service", "product", "expense", "discount", "other"]).default("service"),
  description: z.string().min(1, "Description required"),
  quantity: z.coerce.number().min(1),
  unit_of_measure: z.coerce.number().min(0.001).default(1),
  unit_label: z.string().default(""),
  unit_price: z.coerce.number().min(0),
  sort_order: z.number().default(0),
});

const quotationSchema = z.object({
  company: z.string().min(1, "Company required"),
  client: z.string().optional(),
  client_salutation: z.enum(["Mr", "Mrs", "Miss", "Ms", "Dr", "Prof", "Mx", ""]).default(""),
  client_name: z.string().min(1, "Client name required"),
  client_email: z.string().email().optional().or(z.literal("")),
  client_phone: z.string().optional(),
  client_address:   z.string().optional(),
  client_vat_number: z.string().optional(),
  currency:         z.string().default("KES"),
  issue_date:       z.string().min(1),
  validity_period:  z.string().default("30"),
  due_date:         z.string().min(1),
  notes:            z.string().optional(),
  terms:            z.string().optional(),
  line_items:       z.array(lineItemSchema).min(1, "Add at least one item line"),

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

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<"split" | "editor">("split");
  const [activeTemplate, setActiveTemplate] = useState<string>("modern");

  const [isManualCompany, setIsManualCompany] = useState(false);
  const [isManualClient, setIsManualClient] = useState(false);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data: clientsData } = useQuery({
    queryKey: ["clients", company?.id],
    queryFn: () => companiesApi.members.list(company?.id ?? ""),
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
      client_salutation: "",
      client_name: "",
      client_email: "",
      client_phone: "",
      client_address: "",
      client_vat_number: "",
      currency: company?.currency ?? "KES",
      issue_date: new Date().toISOString().split("T")[0],
      validity_period: "30",
      due_date: new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
      line_items: [{ item_type: "service", description: "", quantity: 1, unit_of_measure: 1, unit_label: "", unit_price: 0, sort_order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });

  const selectedClientId = watch("client");
  const watchedItems = watch("line_items") || [];
  const currencySymbol = watch("currency") || "KES";
  const issueDateWatch = watch("issue_date");
  const validityPeriodWatch = watch("validity_period");

  const manualCompanyName = watch("raw_company_name");
  const manualCompanyAddress = watch("raw_company_address");
  const manualCompanyCity = watch("raw_company_city");
  const manualLocationNumber = watch("raw_company_location_number");

  const clientSalutation = watch("client_salutation");
  const clientName = watch("client_name");
  const clientEmail = watch("client_email");
  const clientPhone = watch("client_phone");
  const clientAddress = watch("client_address");

  // Dynamic profile configuration hook dependencies updates image fallbacks
  useEffect(() => {
    if (company && company.logo_url && !logoPreview) {
      setLogoPreview(company.logo_url);
    }
  }, [company, logoPreview]);

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
        setValue("client_name", match.user_full_name || "");
        setValue("client_email", match.user_email || "");
      }
    }
  }, [selectedClientId, clients, isManualClient, setValue]);

  useEffect(() => {
    if (company && !isEditing) {
      setValue("company", company.id);
      setValue("currency", company.currency || "KES");
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

      if (aiPrefillData.extracted_salutation) {
        setValue("client_salutation", aiPrefillData.extracted_salutation.replace(/\./g, "") as any);
      }

      if (aiPrefillData.extracted_client_name) {
        setValue("client_name", aiPrefillData.extracted_client_name);
      }

      if (aiPrefillData.extracted_currency) {
        setValue("currency", aiPrefillData.extracted_currency);
      }

      if (Array.isArray(aiPrefillData.extracted_items) && aiPrefillData.extracted_items.length > 0) {
        setValue("line_items", aiPrefillData.extracted_items.map((item: any, idx: number) => ({
          item_type: "service",
          description: item.description || "Parsed Estimate Item",
          quantity: Number(item.quantity) || 1,
          unit_of_measure: Number(item.unit_of_measure) || 1,
          unit_label: item.unit_label || "",
          unit_price: Number(item.unit_price) || 0,
          sort_order: idx
        })));
      }
    }
  }, [aiPrefillData, isEditing, setValue]);

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setLogoPreview(url);
    }
  };

  const totalAmount = watchedItems.reduce((sum, item) => {
    const qty = item?.quantity || 0;
    const factor = item?.unit_of_measure || 1;
    const price = item?.unit_price || 0;
    return sum + (qty * factor * price);
  }, 0);

  const saveMutation = useMutation({
    mutationFn: (values: QuotationFormValues) => {
      const { raw_company_name, raw_company_address, raw_company_city, raw_company_location_number, validity_period, ...rest } = values;
      const payload = {
        ...rest,
        line_items: (values.line_items || []).map((item, idx) => ({
          ...item,
          sort_order: idx
        }))
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

      {/* Header bar */}
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

          {/* Provider block + dynamic file context binding icon upload element */}
          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <h3 className="font-bold text-slate-800 text-xs sm:text-sm flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-600" /> Quotation Provider Identity
              </h3>
              <button type="button" onClick={() => setIsManualCompany(!isManualCompany)} className="text-[11px] font-bold text-indigo-600 hover:underline bg-indigo-50 px-2 py-1 rounded">
                {isManualCompany ? "Use Saved Database Profile" : "Type Dynamic Company Info (No Save)"}
              </button>
            </div>

            {/* DYNAMIC ICON IMAGE COMPONENT ENVELOPE INPUT CONTROL */}
            <div className="flex items-center gap-4 bg-slate-50 p-4 rounded-xl border border-gray-100">
              <div
                onClick={() => fileInputRef.current?.click()}
                className="w-14 h-14 bg-white border border-gray-200 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-gray-100 transition-all overflow-hidden group relative"
              >
                {logoPreview ? (
                  <img src={logoPreview} alt="Logo" className="w-full h-full object-cover" />
                ) : (
                  <ImageIcon className="w-5 h-5 text-gray-400 group-hover:text-indigo-600 transition-colors" />
                )}
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-[8px] text-white font-bold transition-all">Change</div>
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-800">Quotation Brand Icon</h4>
                <p className="text-[10px] text-gray-400 mt-0.5">Click preview slot box to upload temporary brand mark image asset.</p>
              </div>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleLogoChange}
                accept="image/*"
                className="hidden"
              />
            </div>

            {isManualCompany ? (
              <div className="space-y-3 animate-fade-in">
                <div>
                  <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Company Name Override</label>
                  <input type="text" {...register("raw_company_name")} placeholder="e.g. Afroshield Roofing Limited" className="w-full text-xs border border-gray-200 rounded-xl p-2.5 focus:border-indigo-500 bg-white" />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" {...register("raw_company_address")} placeholder="Street / Building Address" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
                  <input type="text" {...register("raw_company_city")} placeholder="City" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
                </div>
                <input type="text" {...register("raw_company_location_number")} placeholder="Location / Contact Phone" className="w-full text-xs border border-gray-200 rounded-xl p-2.5" />
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

          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs space-y-4">
            <h3 className="font-bold text-slate-800 text-xs sm:text-sm pb-2 border-b border-gray-100 flex items-center gap-2">
              <User className="w-4 h-4 text-violet-600" /> Target Assignee
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Salutation</label>
                <select {...register("client_salutation")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                  <option value="">(None)</option>
                  {["Mr", "Mrs", "Miss", "Ms", "Dr", "Prof", "Mx"].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Client Contact Name</label>
                <input type="text" {...register("client_name")} placeholder="Type customer representative name..." className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="sm:col-span-1">
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Link Account Profile</label>
                <select {...register("client")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white">
                  <option value="">Link platform user...</option>
                  {clients.map(c => <option key={c.id} value={c.id}>{c.user_full_name}</option>)}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Email Address</label>
                <input type="email" {...register("client_email")} placeholder="client@company.com" className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Contact Phone</label>
                <input type="text" {...register("client_phone")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Building Address</label>
                <input type="text" {...register("client_address")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Tax / VAT Number</label>
                <input type="text" {...register("client_vat_number")} className="w-full border border-gray-200 rounded-xl px-3 py-2 text-sm bg-white" />
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

          <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs">
            <h3 className="font-bold text-slate-800 text-xs sm:text-sm mb-3">Line Pricing Items</h3>
            <div className="space-y-4">
              {fields.map((field, index) => (
                <div key={field.id} className="space-y-2 bg-slate-50/50 p-3 rounded-xl border border-gray-100">
                  <div className="flex flex-col sm:flex-row items-center gap-2">
                    <select {...register(`line_items.${index}.item_type`)} className="w-full sm:w-28 border border-gray-200 rounded-lg p-2 text-xs bg-white">
                      <option value="service">Service</option>
                      <option value="product">Product</option>
                      <option value="expense">Expense</option>
                      <option value="discount">Discount</option>
                      <option value="other">Other</option>
                    </select>
                    <input {...register(`line_items.${index}.description` as const)} placeholder="Item description breakdown..." className="w-full flex-1 border border-gray-200 rounded-lg px-2.5 py-1.5 text-sm bg-white" />
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <input type="number" step="any" {...register(`line_items.${index}.quantity` as const)} placeholder="Qty" className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center bg-white" />
                    <input type="number" step="any" {...register(`line_items.${index}.unit_of_measure` as const)} placeholder="Multiplier" className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center bg-white" />
                    <input type="text" {...register(`line_items.${index}.unit_label` as const)} placeholder="Label (m, kg)" className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-center bg-white" />
                  </div>
                  <div className="flex justify-end gap-2 items-center">
                    <span className="text-[10px] text-gray-400 font-bold uppercase">Price Per Unit:</span>
                    <input type="number" step="0.01" {...register(`line_items.${index}.unit_price` as const)} placeholder="Price" className="w-32 border border-gray-200 rounded-lg px-2 py-1.5 text-sm text-right bg-white" />
                  </div>
                </div>
              ))}
            </div>
            <button type="button" onClick={() => append({ item_type: "service", description: "", quantity: 1, unit_of_measure: 1, unit_label: "", unit_price: 0, sort_order: fields.length })} className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 px-3 py-1.5 rounded-lg transition-colors">
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

        {/* LIVE PREVIEW CANVAS */}
        {previewMode === "split" && (
          <div className="hidden xl:flex flex-col gap-4 sticky top-6 self-start w-full">
            <div className="bg-white p-4 rounded-2xl border border-gray-100 shadow-xs">
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "modern", name: "1. Modern Split" },
                  { id: "leftbar", name: "2. Bold Leftbar" },
                  { id: "clean", name: "3. Minimal Inline" },
                  { id: "headerblock", name: "4. Colored Header" },
                  { id: "framed", name: "5. Technical Box" },
                  { id: "darkcard", name: "6. Cyber Terminal" }
                ].map((tpl) => (
                  <button
                    key={tpl.id}
                    type="button"
                    onClick={() => setActiveTemplate(tpl.id)}
                    className={cn(
                      "text-center px-3 py-2.5 rounded-xl text-xs border transition-all font-bold tracking-tight",
                      activeTemplate === tpl.id ? "border-slate-900 bg-slate-900 text-white shadow-sm" : "border-gray-100 bg-gray-50 text-slate-600"
                    )}
                  >
                    {tpl.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="w-full">
              {/* LAYOUT 1: MODERN SPLIT */}
              {activeTemplate === "modern" && (
                <div className="bg-white rounded-3xl border border-slate-100 p-8 shadow-md text-xs text-slate-700 min-h-[700px] flex flex-col justify-between">
                  <div>
                    <div className="flex justify-between items-start border-b border-slate-100 pb-6 mb-6">
                      <div className="space-y-2.5">
                        {/* FALLBACK BRAND ICON BINDING SLOT RENDERS ACROSS ALL MODALS RECONSTRUCTS LOGO OR FIRST GLYPH CHARACTER */}
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-12 h-12 rounded-xl object-cover border border-gray-100 shadow-xs" />
                        ) : (
                          <div className="w-12 h-12 rounded-xl flex items-center justify-center font-black text-lg bg-indigo-600 text-white shadow-sm">
                            {(manualCompanyName || company?.name || "A")[0]}
                          </div>
                        )}
                        <div>
                          <h4 className="font-bold text-slate-900 text-sm">{manualCompanyName || company?.name || "Afroshield Roofing Limited"}</h4>
                          <p className="text-gray-400 text-[11px] font-medium flex items-center gap-0.5"><MapPin className="w-3 h-3 text-slate-300" /> {manualCompanyAddress || company?.address_line1 || "1231 Karatina"}</p>
                          {company?.email && <p className="text-slate-400 text-[11px] mt-0.5">✉ {company.email}</p>}
                        </div>
                      </div>
                      <div className="text-right">
                        <h2 className="text-xl font-black text-slate-900 uppercase tracking-tight">ESTIMATE STATEMENT</h2>
                        <p className="font-mono text-gray-400 font-bold text-sm">QT-{new Date().getFullYear()}-DYNAMIC</p>
                      </div>
                    </div>
                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 mb-6 grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-[9px] font-bold text-gray-400 uppercase tracking-wide">Quotation Target Representative</p>
                        <p className="text-sm font-bold text-slate-900 mt-1">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Miss Sharlyne Cherono"}</p>
                        {clientAddress && <p className="text-slate-500 text-[11px] mt-0.5">📍 {clientAddress}</p>}
                      </div>
                      <div className="text-right space-y-0.5 self-end font-mono text-[11px] text-slate-500">
                        {clientEmail && <p>✉ {clientEmail}</p>}
                        {clientPhone && <p>📞 {clientPhone}</p>}
                      </div>
                    </div>
                    <table className="w-full text-left border-collapse mb-6">
                      <thead>
                        <tr className="bg-slate-900 text-white text-[9px] uppercase font-bold tracking-wider">
                          <th className="p-3 rounded-tl-lg">Task Description</th>
                          <th className="p-3 text-center">Qty / Measure Matrix</th>
                          <th className="p-3 text-right rounded-tr-lg">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 font-medium">
                        {watchedItems.map((item, i) => (
                          <tr key={i} className="text-slate-800 text-[11px]">
                            <td className="p-3 font-semibold">{item.description || "Testing"}</td>
                            <td className="p-3 text-center text-gray-400 font-mono">{(item.quantity || 0)} {item.unit_of_measure !== 1 && `(× ${item.unit_of_measure} ${item.unit_label || "units"})`}</td>
                            <td className="p-3 text-right text-slate-900 font-bold">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex justify-end border-t border-gray-100 pt-4">
                    <div className="w-72 bg-slate-50 p-3 rounded-xl border border-gray-100 flex items-center justify-between gap-4 font-black text-slate-900">
                      <span className="text-xs uppercase tracking-wider text-slate-400">Total Budgeted Value</span>
                      <span className="text-sm text-indigo-600 font-mono">{formatCurrency(totalAmount, currencySymbol)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* LAYOUT 2: BOLD LEFTBAR */}
              {activeTemplate === "leftbar" && (
                <div className="bg-white rounded-3xl border border-gray-200 shadow-md min-h-[700px] flex overflow-hidden text-xs">
                  <div className="w-1/3 bg-slate-900 text-slate-300 p-6 flex flex-col justify-between border-r border-slate-900">
                    <div className="space-y-6">
                      <div className="space-y-2">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded-xl object-cover bg-white p-0.5" />
                        ) : (
                          <div className="w-10 h-10 bg-white text-slate-950 font-black flex items-center justify-center text-sm rounded-xl">{(manualCompanyName || company?.name || "A")[0]}</div>
                        )}
                        <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">PRODUCER</div>
                        <h4 className="font-black text-white text-base mt-1 truncate">{manualCompanyName || company?.name || "Afroshield Roofing"}</h4>
                        <p className="text-[11px] text-slate-400 mt-1">{manualCompanyAddress || "1231 Karatina"}</p>
                      </div>
                      <div className="border-t border-slate-800 pt-4 space-y-1">
                        <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">ASSIGNED TO</div>
                        <p className="text-sm font-bold text-white mt-1">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Sharlyne Cherono"}</p>
                        {clientAddress && <p className="text-slate-400 text-[11px]">📍 {clientAddress}</p>}
                        {clientPhone && <p className="text-slate-400 text-[11px]">📞 {clientPhone}</p>}
                      </div>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">ID: QT-{new Date().getFullYear()}</div>
                  </div>
                  <div className="w-2/3 p-8 flex flex-col justify-between bg-white">
                    <div>
                      <div className="flex justify-between items-baseline mb-6 border-b border-gray-100 pb-4">
                        <h2 className="text-lg font-black text-slate-900 tracking-tight">PROPOSAL BRIEF</h2>
                        <span className="font-mono text-slate-400 font-bold">EST-992</span>
                      </div>
                      <div className="space-y-4">
                        {watchedItems.map((item, i) => (
                          <div key={i} className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-gray-100">
                            <div>
                              <p className="font-bold text-slate-900 text-[11px]">{item.description || "Line Item Description"}</p>
                              <p className="text-[10px] text-gray-400 font-mono">Count: {item.quantity} {item.unit_of_measure !== 1 && `(× ${item.unit_of_measure})`}</p>
                            </div>
                            <span className="font-bold text-slate-900">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="pt-4 border-t border-gray-100 flex flex-col items-end">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">GRAND TOTAL BUDGET</span>
                      <span className="text-xl font-black text-slate-900 mt-1">{formatCurrency(totalAmount, currencySymbol)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* LAYOUT 3: MINIMAL INLINE */}
              {activeTemplate === "clean" && (
                <div className="bg-neutral-50 rounded-3xl border border-neutral-200 p-8 min-h-[700px] flex flex-col justify-between text-neutral-800 tracking-tight">
                  <div className="space-y-8">
                    <div className="flex justify-between items-start">
                      <div className="flex flex-col space-y-1">
                        <span className="text-xs uppercase font-mono tracking-widest text-neutral-400">Proposal Statement</span>
                        <h1 className="text-2xl font-light text-neutral-900">{manualCompanyName || company?.name || "Afroshield Roofing Limited"}</h1>
                        <p className="text-xs text-neutral-400 font-mono">{manualCompanyAddress || "1231 Karatina"}</p>
                      </div>
                      {logoPreview ? (
                        <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded border border-neutral-300 object-cover" />
                      ) : (
                        <div className="w-10 h-10 border border-neutral-900 rounded flex items-center justify-center font-bold text-sm">{(manualCompanyName || company?.name || "A")[0]}</div>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-4 border-y border-neutral-200 py-4 text-xs font-mono">
                      <div>
                        <span className="block text-neutral-400">Prepared For:</span>
                        <span className="font-bold text-neutral-900">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Sharlyne Cherono"}</span>
                        {clientAddress && <span className="block text-neutral-500 mt-0.5">📍 {clientAddress}</span>}
                        {clientPhone && <span className="block text-neutral-500">📞 {clientPhone}</span>}
                      </div>
                      <div className="text-right">
                        <span className="block text-neutral-400">Date Issued:</span>
                        <span className="font-bold text-neutral-900">{new Date().toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {watchedItems.map((item, i) => (
                        <div key={i} className="flex justify-between items-baseline py-2 border-b border-neutral-200/60 font-medium">
                          <span className="text-neutral-700">{item.description || "Item line"} <span className="text-xs font-mono text-neutral-400">({item.quantity} units {item.unit_of_measure !== 1 && `× ${item.unit_of_measure}`})</span></span>
                          <span className="font-mono text-neutral-900">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex justify-between items-baseline pt-6 border-t-2 border-neutral-900 font-mono">
                    <span className="text-sm font-bold text-neutral-900 uppercase">Aggregated Value:</span>
                    <span className="text-xl font-bold text-neutral-900">{formatCurrency(totalAmount, currencySymbol)}</span>
                  </div>
                </div>
              )}

              {/* LAYOUT 4: COLORED HEADER */}
              {activeTemplate === "headerblock" && (
                <div className="bg-white rounded-3xl border border-gray-100 shadow-md min-h-[700px] overflow-hidden flex flex-col justify-between text-xs">
                  <div>
                    <div className="bg-gradient-to-r from-violet-600 to-indigo-700 p-8 text-white flex justify-between items-center">
                      <div className="flex items-center gap-3">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded-xl object-cover bg-white/20 p-0.5" />
                        ) : (
                          <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center font-black text-sm">{(manualCompanyName || company?.name || "A")[0]}</div>
                        )}
                        <div>
                          <h2 className="text-lg font-black tracking-tight">{manualCompanyName || company?.name || "Afroshield Roofing Limited"}</h2>
                          <p className="text-violet-100 text-[11px] mt-1 opacity-90">{manualCompanyAddress || "1231 Karatina"}</p>
                        </div>
                      </div>
                      <div className="text-right bg-white/10 px-4 py-2 rounded-xl backdrop-blur-xs">
                        <span className="block text-[9px] font-bold text-violet-200 uppercase tracking-widest">TOTAL VALUE</span>
                        <span className="text-base font-black font-mono">{formatCurrency(totalAmount, currencySymbol)}</span>
                      </div>
                    </div>
                    <div className="p-8">
                      <div className="mb-6 border-l-4 border-indigo-600 pl-4 py-1 grid grid-cols-2 gap-4">
                        <div>
                          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Client Representative Target</span>
                          <h4 className="text-sm font-black text-slate-900 mt-0.5">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Miss Sharlyne Cherono"}</h4>
                          {clientAddress && <p className="text-slate-500 text-[11px] mt-0.5">📍 {clientAddress}</p>}
                        </div>
                        <div className="text-right font-mono text-[10px] text-slate-400 space-y-0.5">
                          {clientEmail && <p>{clientEmail}</p>}
                          {clientPhone && <p>📞 {clientPhone}</p>}
                        </div>
                      </div>
                      <table className="w-full border-collapse text-left">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase text-[9px]">
                            <th className="py-3">Scope Target Block</th>
                            <th className="py-3 text-center">Volume Matrix</th>
                            <th className="py-3 text-right">Budget Valuation</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {watchedItems.map((item, i) => (
                            <tr key={i} className="text-slate-700">
                              <td className="py-3.5 font-bold text-slate-900">{item.description || "Pricing Item Breakdown"}</td>
                              <td className="py-3.5 text-center font-mono text-slate-400">{item.quantity} {item.unit_of_measure !== 1 && `(× ${item.unit_of_measure})`}</td>
                              <td className="py-3.5 text-right font-bold text-indigo-600">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="p-8 bg-slate-50 border-t border-slate-100 flex justify-between items-center text-[11px]">
                    <span className="text-slate-400 font-bold">Proposal Baseline Engine Statement v1.04</span>
                    <span className="font-mono text-slate-900 font-bold">Ready for conversion</span>
                  </div>
                </div>
              )}

              {/* LAYOUT 5: TECHNICAL BOX */}
              {activeTemplate === "framed" && (
                <div className="bg-white rounded-3xl border-2 border-slate-950 p-6 min-h-[700px] flex flex-col justify-between font-mono text-slate-900 text-xs">
                  <div className="space-y-6">
                    <div className="border-b-2 border-slate-950 pb-4 flex justify-between items-end">
                      <div className="flex items-center gap-2">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-8 h-8 object-cover border border-slate-950" />
                        ) : (
                          <div className="w-8 h-8 bg-slate-950 text-white font-black flex items-center justify-center text-xs">{(manualCompanyName || company?.name || "A")[0]}</div>
                        )}
                        <div>
                          <div className="text-sm font-black">[BLUEPRINT SCHEMATIC]</div>
                          <h3 className="font-bold text-slate-800 mt-1 text-xs uppercase">{manualCompanyName || company?.name || "Afroshield Roofing"}</h3>
                        </div>
                      </div>
                      <span className="text-right font-bold bg-slate-950 text-white px-2 py-0.5">EST-MODE-A</span>
                    </div>
                    <div className="border border-slate-300 p-3 grid grid-cols-2 gap-4 bg-slate-50/50 text-[11px]">
                      <div>
                        <span className="text-[10px] text-slate-400 block">TAG_CLIENT_REPRESENTATIVE:</span>
                        <span className="font-bold">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Sharlyne Cherono"}</span>
                        {clientAddress && <span className="block text-slate-500">{clientAddress}</span>}
                      </div>
                      <div className="text-right space-y-0.5">
                        {clientEmail && <span className="block">{clientEmail}</span>}
                        {clientPhone && <span className="block">📞 {clientPhone}</span>}
                      </div>
                    </div>
                    <div className="border border-slate-950 rounded-lg overflow-hidden">
                      <div className="bg-slate-100 p-2 font-bold border-b border-slate-950 grid grid-cols-3 text-[10px]">
                        <span>ITEM_SPECIFICATION</span>
                        <span className="text-center">METRIC_QTY</span>
                        <span className="text-right">VAL_MATRIX</span>
                      </div>
                      {watchedItems.map((item, i) => (
                        <div key={i} className="p-2.5 grid grid-cols-3 border-b border-slate-200 last:border-0 bg-white items-center">
                          <span className="font-bold truncate">{item.description || "Task Item Specification"}</span>
                          <span className="text-center text-slate-500">{item.quantity} {item.unit_of_measure !== 1 && `[×${item.unit_of_measure}]`}</span>
                          <span className="text-right font-bold">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border-t-2 border-slate-950 pt-4 flex justify-between items-center bg-slate-100/40 p-3 rounded-xl border border-slate-200">
                    <span className="font-black uppercase tracking-wide">SUM_TOTAL_VAL:</span>
                    <span className="text-base font-black px-3 py-1 bg-slate-950 text-white rounded-md">{formatCurrency(totalAmount, currencySymbol)}</span>
                  </div>
                </div>
              )}

              {/* LAYOUT 6: CYBER TERMINAL */}
              {activeTemplate === "darkcard" && (
                <div className="bg-slate-950 rounded-3xl border border-slate-800 p-8 min-h-[700px] flex flex-col justify-between font-mono text-emerald-400 text-xs">
                  <div className="space-y-6">
                    <div className="flex justify-between items-start border-b border-slate-800 pb-4">
                      <div className="flex items-center gap-3">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 border border-emerald-500/20 object-cover rounded" />
                        ) : (
                          <div className="w-10 h-10 border border-emerald-500/30 bg-emerald-500/10 flex items-center justify-center font-black text-white">{(manualCompanyName || company?.name || "A")[0]}</div>
                        )}
                        <div>
                          <span className="text-slate-500 block text-[10px] font-bold">// SYSTEM CORE CORPORATE INSTANCE</span>
                          <h2 className="text-sm font-bold text-white mt-0.5">{manualCompanyName || company?.name || "Afroshield Roofing"}</h2>
                        </div>
                      </div>
                    </div>
                    <div className="bg-slate-900/60 p-4 rounded-xl border border-slate-800 space-y-1 text-slate-300">
                      <span className="text-slate-500 text-[10px] block font-bold"># STAGE QUERY OVERRIDES PARAMETERS:</span>
                      <p><span className="text-emerald-500">client_target_name</span> = "{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Miss Sharlyne Cherono"}"</p>
                      {clientAddress && <p><span className="text-slate-500">client_addr</span> = "{clientAddress}"</p>}
                      {clientPhone && <p><span className="text-slate-500">client_phone</span> = "{clientPhone}"</p>}
                    </div>
                    <div className="space-y-2">
                      {watchedItems.map((item, i) => (
                        <div key={i} className="flex justify-between items-center bg-slate-900/40 p-3 rounded-lg border border-slate-900/80 font-mono">
                          <div>
                            <span className="text-white block">{item.description || "Schema item trace…"}</span>
                            <span className="text-[10px] text-slate-500">QUANTITY: {item.quantity} {item.unit_of_measure !== 1 && `[MEASURE: ${item.unit_of_measure}]`}</span>
                          </div>
                          <span className="text-emerald-300 font-bold">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencySymbol)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border-t border-slate-800 pt-4 flex justify-between items-center bg-slate-900/50 p-3 rounded-xl border border-slate-800/80">
                    <span className="text-slate-500 font-bold uppercase tracking-wider">NET_AGGREGATE_VALUE:</span>
                    <span className="text-base font-bold text-white tracking-tight">{formatCurrency(totalAmount, currencySymbol)}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}