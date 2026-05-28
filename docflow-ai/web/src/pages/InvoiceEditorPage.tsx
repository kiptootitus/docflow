import { useState, useEffect, useRef } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Save, Eye, LayoutGrid, Building2, Calendar, MapPin, UserCheck, Palette, Image as ImageIcon } from "lucide-react";
import { companiesApi, invoicesApi } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const lineItemSchema = z.object({
  item_type:        z.enum(["service", "product", "expense", "discount", "other"]).default("service"),
  description:      z.string().min(1, "Description required"),
  quantity:         z.coerce.number().min(0.001),
  unit_of_measure:  z.coerce.number().min(0.001).default(1),
  unit_label:       z.string().default(""),
  unit_price:       z.coerce.number().min(0),
  discount_percent: z.coerce.number().min(0).max(100).default(0),
  tax_rate:         z.coerce.number().min(0).default(0),
  sort_order:       z.number().default(0),
});

const invoiceSchema = z.object({
  company:          z.string().min(1, "Company required"),
  client:           z.string().optional(),
  client_salutation: z.enum(["Mr", "Mrs", "Miss", "Ms", "Dr", "Prof", "Mx", ""]).default(""),
  client_name:      z.string().optional(),
  client_email:     z.string().email().optional().or(z.literal("")),
  client_phone:     z.string().optional(),
  client_address:   z.string().optional(),
  client_vat_number: z.string().optional(),
  currency:         z.string().default("KES"),
  issue_date:       z.string().min(1),
  due_date:         z.string().min(1),
  notes:            z.string().optional(),
  terms:            z.string().optional(),
  discount_amount:  z.coerce.number().default(0),
  line_items:       z.array(lineItemSchema).min(1, "Include at least one line item"),
});

type InvoiceFormValues = z.infer<typeof invoiceSchema>;

export default function InvoiceEditorPage() {
  const { id }          = useParams();
  const navigate        = useNavigate();
  const location        = useLocation();
  const queryClient     = useQueryClient();
  const isEditing       = Boolean(id);
  const aiPrefillData   = location.state?.prefill;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"editor" | "split">("split");
  const [activeTemplate, setActiveTemplate] = useState<string>("modern");

  const { data: companiesData } = useQuery({
    queryKey: ["companies"],
    queryFn:  () => companiesApi.list(),
  });
  const company = companiesData?.data?.results?.[0];

  const { register, control, handleSubmit, watch, setValue } =
    useForm<InvoiceFormValues>({
      resolver: zodResolver(invoiceSchema),
      defaultValues: {
        company:          company?.id ?? "",
        client_salutation: "",
        currency:         "KES",
        issue_date:       new Date().toISOString().split("T")[0],
        due_date:         new Date(Date.now() + 14 * 86400000).toISOString().split("T")[0],
        discount_amount:  0,
        line_items:       [{ item_type: "service", description: "", quantity: 1, unit_of_measure: 1, unit_label: "", unit_price: 0, discount_percent: 0, tax_rate: 0, sort_order: 0 }],
      },
    });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });

  useEffect(() => {
    if (company && company.logo_url && !logoPreview) {
      setLogoPreview(company.logo_url);
    }
  }, [company, logoPreview]);

  useEffect(() => {
    if (company && !isEditing) {
      setValue("company",  company.id);
      setValue("currency", company.currency || "KES");
    }
  }, [company, isEditing, setValue]);

  useEffect(() => {
    if (!aiPrefillData || isEditing) return;

    if (aiPrefillData.extracted_client_name)
      setValue("client_name", aiPrefillData.extracted_client_name);
    if (aiPrefillData.extracted_currency)
      setValue("currency", aiPrefillData.extracted_currency);
    if (aiPrefillData.extracted_salutation)
      setValue("client_salutation", aiPrefillData.extracted_salutation.replace(/\./g, "") as any);
    if (Array.isArray(aiPrefillData.extracted_items) && aiPrefillData.extracted_items.length > 0) {
      setValue("line_items", aiPrefillData.extracted_items.map((item: any, idx: number) => ({
        item_type:        "service",
        description:      item.description || "Extracted Item",
        quantity:         Number(item.quantity)   || 1,
        unit_of_measure:  Number(item.unit_of_measure) || 1,
        unit_label:       item.unit_label || "",
        unit_price:       Number(item.unit_price) || 0,
        discount_percent: 0,
        tax_rate:         0,
        sort_order:       idx,
      })));
    }
  }, [aiPrefillData, isEditing, setValue]);

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const url = URL.createObjectURL(file);
      setLogoPreview(url);
    }
  };

  const watchedLineItems  = watch("line_items") || [];
  const currencyToken     = watch("currency") || "KES";
  const discountDeduction = watch("discount_amount") || 0;

  const clientSalutation  = watch("client_salutation");
  const clientName        = watch("client_name");
  const clientEmail       = watch("client_email");
  const clientPhone       = watch("client_phone");
  const clientAddress     = watch("client_address");
  const clientVat         = watch("client_vat_number");

  const subtotalAmount = watchedLineItems.reduce(
    (acc, row) => {
      const qty = row?.quantity || 0;
      const factor = row?.unit_of_measure || 1;
      const price = row?.unit_price || 0;
      return acc + (qty * factor * price);
    },
    0,
  );

  const vatRate        = company?.vat_config ? parseFloat((company as any).vat_config?.vat_rate || "0") : 0;
  const calculatedTax  = subtotalAmount * (vatRate / 100);
  const grandTotal     = subtotalAmount + calculatedTax - discountDeduction;

  const saveMutation = useMutation({
    mutationFn: (values: InvoiceFormValues) => {
      const { client, ...rest } = values;
      const payload: Record<string, any> = { ...rest };
      if (client) payload.client = client;

      payload.line_items = (values.line_items || []).map((item, idx) => ({
        item_type:        item.item_type,
        description:      item.description,
        quantity:         item.quantity,
        unit_of_measure:  item.unit_of_measure,
        unit_label:       item.unit_label,
        unit_price:       item.unit_price,
        discount_percent: item.discount_percent ?? 0,
        tax_rate:         item.tax_rate ?? 0,
        sort_order:       idx,
      }));

      return invoicesApi.create(payload as any);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      navigate("/invoices");
    },
  });

  return (
    <div className="p-4 sm:p-6 max-w-[1600px] mx-auto bg-slate-50/40 min-h-screen font-sans text-slate-800">

      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 bg-white p-4 rounded-2xl border border-slate-100 shadow-xs print:hidden">
        <div className="flex items-center gap-3">
          <button type="button" onClick={() => navigate("/invoices")}
            className="p-2 hover:bg-slate-50 text-slate-500 rounded-xl border border-slate-100">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-lg font-bold">New Invoice</h1>
            <p className="text-slate-400 text-xs">{company?.name ?? "Loading workspace…"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => setViewMode("editor")}
            className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all",
              viewMode === "editor" ? "bg-slate-900 text-white" : "text-slate-400 hover:text-slate-600")}>
            <LayoutGrid className="w-3.5 h-3.5 inline mr-1" />Form
          </button>
          <button type="button" onClick={() => setViewMode("split")}
            className={cn("px-3 py-1.5 rounded-lg text-xs font-bold transition-all",
              viewMode === "split" ? "bg-slate-900 text-white" : "text-slate-400 hover:text-slate-600")}>
            <Eye className="w-3.5 h-3.5 inline mr-1" />Preview
          </button>
        </div>
      </div>

      <div className={cn("grid grid-cols-1 gap-6", viewMode === "split" ? "xl:grid-cols-2" : "max-w-4xl mx-auto")}>

        {/* INPUT FORM BLOCK */}
        <form onSubmit={handleSubmit((data) => saveMutation.mutate(data))} className="space-y-5 print:hidden">
          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-3">
            <div className="flex justify-between items-center pb-2 border-b border-gray-100">
              <h3 className="font-bold text-xs sm:text-sm flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-600" /> Issuing Company
              </h3>
            </div>

            {/* DYNAMIC ICON IMAGE COMPONENT ENVELOPE INPUT CONTROL */}
            <div className="flex items-center gap-4 bg-slate-50 p-4 rounded-xl border border-slate-100">
              <div
                onClick={() => fileInputRef.current?.click()}
                className="w-14 h-14 bg-white border border-slate-200 rounded-xl flex flex-col items-center justify-center cursor-pointer hover:bg-gray-100 transition-all overflow-hidden group relative"
              >
                {logoPreview ? (
                  <img src={logoPreview} alt="Logo" className="w-full h-full object-cover" />
                ) : (
                  <ImageIcon className="w-5 h-5 text-gray-400 group-hover:text-indigo-600 transition-colors" />
                )}
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-[8px] text-white font-bold transition-all">Change</div>
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-800">Invoice Brand Icon</h4>
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

            <div>
              <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Workspace</label>
              <select {...register("company")} className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white">
                <option value={company?.id ?? ""}>{company?.name ?? "Loading…"}</option>
              </select>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs space-y-3">
            <h3 className="font-bold text-xs sm:text-sm flex items-center gap-2 pb-2 border-b border-slate-50">
              <UserCheck className="w-4 h-4 text-violet-600" /> Bill To
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Salutation</label>
                <select {...register("client_salutation")} className="w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white">
                  <option value="">(None)</option>
                  {["Mr", "Mrs", "Miss", "Ms", "Dr", "Prof", "Mx"].map(s => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Client Name</label>
                <input type="text" {...register("client_name")}
                  placeholder="e.g. John Smith"
                  className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:border-indigo-500 bg-white" />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Client Email</label>
                <input type="email" {...register("client_email")}
                  placeholder="billing@acme.com"
                  className="w-full text-xs border border-slate-200 rounded-xl p-2.5 focus:border-indigo-500 bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Phone</label>
                <input type="text" {...register("client_phone")}
                  placeholder="Contact Number"
                  className="w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white" />
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Address</label>
                <input type="text" {...register("client_address")}
                  placeholder="Billing Address Line"
                  className="w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Tax / VAT ID</label>
                <input type="text" {...register("client_vat_number")}
                  placeholder="Client VAT/TIN Number"
                  className="w-full text-xs border border-slate-200 rounded-xl p-2.5 bg-white" />
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-1">
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Currency</label>
                <select {...register("currency")} className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white">
                  {["KES","USD","EUR","GBP"].map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Issue Date</label>
                <input type="date" {...register("issue_date")} className="w-full border border-slate-200 rounded-xl p-2 text-xs bg-white" />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Due Date</label>
                <input type="date" {...register("due_date")} className="w-full border border-slate-200 rounded-xl p-2 text-xs bg-white" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs">
            <h3 className="font-bold text-slate-900 text-xs sm:text-sm mb-3">Line Items</h3>
            <div className="space-y-4">
              {fields.map((field, index) => (
                <div key={field.id} className="space-y-2 bg-slate-50/60 p-3 rounded-xl border border-slate-100/60">
                  <div className="flex flex-col sm:flex-row items-center gap-2">
                    <select
                      {...register(`line_items.${index}.item_type`)}
                      className="w-full sm:w-28 border border-slate-200 rounded-lg p-2 text-xs bg-white">
                      <option value="service">Service</option>
                      <option value="product">Product</option>
                      <option value="expense">Expense</option>
                      <option value="discount">Discount</option>
                      <option value="other">Other</option>
                    </select>
                    <input
                      {...register(`line_items.${index}.description`)}
                      placeholder="Item description breakdowns…"
                      className="w-full sm:flex-1 border border-slate-200 rounded-lg p-2 text-xs bg-white" />
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div>
                      <label className="block text-[9px] font-bold text-slate-400 uppercase mb-0.5">Quantity</label>
                      <input type="number" step="any"
                        {...register(`line_items.${index}.quantity`)}
                        placeholder="Qty"
                        className="w-full border border-slate-200 rounded-lg p-1.5 text-xs text-center bg-white" />
                    </div>
                    <div>
                      <label className="block text-[9px] font-bold text-slate-400 uppercase mb-0.5">Measure Multiplier</label>
                      <input type="number" step="any"
                        {...register(`line_items.${index}.unit_of_measure`)}
                        placeholder="e.g. 23"
                        className="w-full border border-slate-200 rounded-lg p-1.5 text-xs text-center bg-white" />
                    </div>
                    <div>
                      <label className="block text-[9px] font-bold text-slate-400 uppercase mb-0.5">Unit Label</label>
                      <input type="text"
                        {...register(`line_items.${index}.unit_label`)}
                        placeholder="e.g. m, kg"
                        className="w-full border border-slate-200 rounded-lg p-1.5 text-xs text-center bg-white" />
                    </div>
                    <div>
                      <label className="block text-[9px] font-bold text-slate-400 uppercase mb-0.5">Rate / Price</label>
                      <input type="number" step="0.01"
                        {...register(`line_items.${index}.unit_price`)}
                        placeholder="Per Unit Rate"
                        className="w-full border border-slate-200 rounded-lg p-1.5 text-xs text-right bg-white" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <button type="button"
              onClick={() => append({ item_type: "service", description: "", quantity: 1, unit_of_measure: 1, unit_label: "", unit_price: 0, discount_percent: 0, tax_rate: 0, sort_order: fields.length })}
              className="mt-3 text-xs font-bold text-indigo-600 bg-indigo-50 px-3 py-1.5 rounded-lg inline-flex items-center gap-1">
              <Plus className="w-3.5 h-3.5" /> Add Item
            </button>
          </div>

          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-xs">
            <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">Notes to client</label>
            <textarea {...register("notes")} rows={3}
              className="w-full border border-slate-200 rounded-xl p-2.5 text-xs bg-white resize-none" />
          </div>

          <div className="bg-slate-950 rounded-2xl p-5 text-white flex justify-between items-center shadow-md">
            <div>
              <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wide">Estimated Total</span>
              <h2 className="text-xl font-black text-indigo-400">
                {currencyToken} {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
              </h2>
            </div>
            <button type="submit" disabled={saveMutation.isPending}
              className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-bold px-5 py-2.5 rounded-xl flex items-center gap-1.5">
              <Save className="w-4 h-4" /> Save Invoice
            </button>
          </div>
        </form>

        {/* DESIGN PREVIEW BLUEPRINT ENGINE */}
        {viewMode === "split" && (
          <div className="hidden xl:flex flex-col gap-4 sticky top-6 self-start w-full">
            <div className="bg-white p-3 rounded-2xl border border-slate-100 shadow-xs">
              <div className="grid grid-cols-3 gap-1.5">
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
                      "text-center py-2 rounded-xl text-xs border transition-all font-bold",
                      activeTemplate === tpl.id ? "bg-slate-900 text-white border-slate-900" : "bg-gray-50 text-slate-600 border-gray-100"
                    )}
                  >
                    {tpl.name}
                  </button>
                ))}
              </div>
            </div>

            {/* BLUEPRINT INTERACTIVE RENDER CANVAS */}
            <div className="w-full">

              {/* TEMPLATE 1: MODERN SPLIT */}
              {activeTemplate === "modern" && (
                <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-md text-xs text-slate-700 min-h-[720px] flex flex-col justify-between">
                  <div>
                    <div className="flex justify-between items-start border-b border-slate-100 pb-6 mb-6">
                      <div className="space-y-2">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-12 h-12 rounded-xl object-cover border border-gray-100 shadow-xs" />
                        ) : (
                          <div className="w-12 h-12 rounded-xl flex items-center justify-center font-black text-lg bg-indigo-600 text-white shadow-sm">
                            {(company?.name || "T")[0]}
                          </div>
                        )}
                        <div>
                          <h4 className="font-bold text-slate-900 text-sm">{company?.name || "Testing Company"}</h4>
                          <p className="text-slate-400 text-[11px] font-medium flex items-center gap-0.5"><MapPin className="w-3 h-3" /> {company?.address_line1 || "Nairobi, Kenya"}</p>
                          {company?.email && <p className="text-slate-400 text-[11px] mt-0.5">✉ {company.email}</p>}
                        </div>
                      </div>
                      <div className="text-right">
                        <h2 className="text-xl font-black text-slate-900 uppercase tracking-tight">TAX INVOICE</h2>
                        <p className="font-mono text-gray-400 font-bold text-sm">INV-{new Date().getFullYear()}-M</p>
                      </div>
                    </div>

                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 mb-6 grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-[9px] font-bold text-gray-400 uppercase tracking-wide">Billed Recipient Details</p>
                        <p className="text-sm font-bold text-slate-900 mt-1">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Titus"}</p>
                        {clientAddress && <p className="text-slate-500 text-[11px] mt-0.5">📍 {clientAddress}</p>}
                      </div>
                      <div className="text-right space-y-0.5 self-end font-mono text-[11px] text-slate-500">
                        {clientEmail && <p>✉ {clientEmail}</p>}
                        {clientPhone && <p>📞 {clientPhone}</p>}
                        {clientVat && <p>Hash ID: {clientVat}</p>}
                      </div>
                    </div>

                    <table className="w-full text-left border-collapse mb-6">
                      <thead>
                        <tr className="bg-slate-900 text-white text-[9px] uppercase font-bold tracking-wider">
                          <th className="p-3 rounded-l-lg">Description</th>
                          <th className="p-3 text-center">Qty / Measure Matrix</th>
                          <th className="p-3 text-right rounded-r-lg">Total</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 font-medium">
                        {watchedLineItems.map((item, i) => {
                          const qty = item.quantity || 0;
                          const uom = item.unit_of_measure || 1;
                          const price = item.unit_price || 0;
                          return (
                            <tr key={i} className="text-slate-800 text-[11px]">
                              <td className="p-3 font-semibold">{item.description || "Watches"}</td>
                              <td className="p-3 text-center text-gray-400 font-mono">{qty} {uom !== 1 && `(× ${uom} ${item.unit_label || "units"})`}</td>
                              <td className="p-3 text-right text-slate-900 font-bold">{formatCurrency(qty * uom * price, currencyToken)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex justify-end border-t border-gray-100 pt-4">
                    <div className="w-72 bg-slate-50 p-3 rounded-xl border border-gray-100 flex items-center justify-between gap-4 font-black text-slate-900">
                      <span className="text-xs uppercase tracking-wider text-slate-400">Total Liability Due</span>
                      <span className="text-sm text-indigo-600 font-mono">{formatCurrency(grandTotal, currencyToken)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* LAYOUT 2: BOLD LEFTBAR */}
              {activeTemplate === "leftbar" && (
                <div className="bg-white rounded-3xl border border-gray-200 shadow-md min-h-[720px] flex overflow-hidden text-xs">
                  <div className="w-1/3 bg-slate-900 text-slate-300 p-6 flex flex-col justify-between border-r border-slate-900">
                    <div className="space-y-6">
                      <div className="space-y-2">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded-xl object-cover bg-white p-0.5" />
                        ) : (
                          <div className="w-10 h-10 rounded-xl flex items-center justify-center font-black bg-white text-slate-950 shadow-sm">{ (company?.name || "T")[0] }</div>
                        )}
                        <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">ISSUER</div>
                        <h4 className="font-black text-white text-base mt-1 truncate">{company?.name || "Testing Company"}</h4>
                        <p className="text-[11px] text-slate-400 mt-1">{company?.address_line1 || "Nairobi, Kenya"}</p>
                      </div>
                      <div className="border-t border-slate-800 pt-4 space-y-1">
                        <div className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">BILL TO RECIPIENT</div>
                        <p className="text-sm font-bold text-white">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Titus"}</p>
                        {clientAddress && <p className="text-slate-400 text-[11px]">📍 {clientAddress}</p>}
                        {clientPhone && <p className="text-slate-400 text-[11px]">📞 {clientPhone}</p>}
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-slate-500">INV-{new Date().getFullYear()}</span>
                  </div>
                  <div className="w-2/3 p-8 flex flex-col justify-between bg-white">
                    <div>
                      <div className="flex justify-between items-baseline mb-6 border-b border-gray-100 pb-4">
                        <h2 className="text-lg font-black text-slate-900 tracking-tight">TAX INVOICE STATEMENT</h2>
                        <span className="font-mono text-slate-400 font-bold">#PREVIEW</span>
                      </div>
                      <div className="space-y-4">
                        {watchedLineItems.map((item, i) => (
                          <div key={i} className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-gray-100">
                            <div>
                              <p className="font-bold text-slate-900 text-[11px]">{item.description || "Watches"}</p>
                              <p className="text-[10px] text-gray-400 font-mono">Volume Count: {item.quantity} {item.unit_of_measure !== 1 && `(× ${item.unit_of_measure})`}</p>
                            </div>
                            <span className="font-bold text-slate-900">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencyToken)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="pt-4 border-t border-gray-100 flex flex-col items-end">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">GRAND TOTAL</span>
                      <span className="text-xl font-black text-slate-900 mt-1">{formatCurrency(grandTotal, currencyToken)}</span>
                    </div>
                  </div>
                </div>
              )}

              {/* LAYOUT 3: MINIMAL INLINE */}
              {activeTemplate === "clean" && (
                <div className="bg-neutral-50 rounded-3xl border border-neutral-200 p-8 min-h-[720px] flex flex-col justify-between text-neutral-800 tracking-tight">
                  <div className="space-y-8">
                    <div className="flex justify-between items-start">
                      <div className="flex flex-col space-y-1">
                        <span className="text-xs uppercase font-mono tracking-widest text-neutral-400">Tax Invoice Receipt</span>
                        <h1 className="text-2xl font-light text-neutral-900">{company?.name || "Testing Company"}</h1>
                        <p className="text-xs text-neutral-400 font-mono">{company?.address_line1 || "Nairobi, Kenya"} {company?.email && `| ${company.email}`}</p>
                      </div>
                      {logoPreview ? (
                        <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded border border-neutral-300 object-cover" />
                      ) : (
                        <div className="w-10 h-10 border border-neutral-900 rounded flex items-center justify-center font-bold text-sm">{(company?.name || "T")[0]}</div>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-4 border-y border-neutral-200 py-4 text-xs font-mono">
                      <div>
                        <span className="block text-neutral-400">Customer Bill Reference:</span>
                        <span className="font-bold text-neutral-900">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Titus"}</span>
                        {clientAddress && <span className="block text-neutral-500 mt-0.5">📍 {clientAddress}</span>}
                        {clientPhone && <span className="block text-neutral-500">📞 {clientPhone}</span>}
                      </div>
                      <div className="text-right">
                        <span className="block text-neutral-400">Date Issued:</span>
                        <span className="font-bold text-neutral-900">{new Date().toLocaleDateString()}</span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {watchedLineItems.map((item, i) => (
                        <div key={i} className="flex justify-between items-baseline py-2 border-b border-neutral-200/60 font-medium">
                          <span className="text-neutral-700">{item.description || "Watches"} <span className="text-xs font-mono text-neutral-400">({item.quantity} units {item.unit_of_measure !== 1 && `× ${item.unit_of_measure}`})</span></span>
                          <span className="font-mono text-neutral-900">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencyToken)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="flex justify-between items-baseline pt-6 border-t-2 border-neutral-900 font-mono">
                    <span className="text-sm font-bold text-neutral-900 uppercase">Aggregated Liability:</span>
                    <span className="text-xl font-bold text-neutral-900">{formatCurrency(grandTotal, currencyToken)}</span>
                  </div>
                </div>
              )}

              {/* LAYOUT 4: COLORED HEADER */}
              {activeTemplate === "headerblock" && (
                <div className="bg-white rounded-3xl border border-gray-100 shadow-md min-h-[720px] overflow-hidden flex flex-col justify-between text-xs">
                  <div>
                    <div className="bg-gradient-to-r from-violet-600 to-indigo-700 p-8 text-white flex justify-between items-center">
                      <div className="flex items-center gap-3">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 rounded-xl object-cover bg-white/20 p-0.5" />
                        ) : (
                          <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center font-black text-sm">{(company?.name || "T")[0]}</div>
                        )}
                        <div>
                          <h2 className="text-lg font-black tracking-tight">{company?.name || "Testing Company"}</h2>
                          <p className="text-violet-100 text-[11px] mt-0.5 opacity-90">{company?.address_line1 || "Nairobi, Kenya"}</p>
                        </div>
                      </div>
                      <div className="text-right bg-white/10 px-4 py-2 rounded-xl backdrop-blur-xs">
                        <span className="block text-[9px] font-bold text-violet-200 uppercase tracking-widest">DUE ACCOUNT LIABILITY</span>
                        <span className="text-base font-black font-mono">{formatCurrency(grandTotal, currencyToken)}</span>
                      </div>
                    </div>
                    <div className="p-8">
                      <div className="mb-6 border-l-4 border-indigo-600 pl-4 py-1 grid grid-cols-2 gap-4">
                        <div>
                          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Billed Recipient Target</span>
                          <h4 className="text-sm font-black text-slate-900 mt-0.5">{clientSalutation ? `${clientSalutation} ` : ""}{clientName || "Titus"}</h4>
                          {clientAddress && <p className="text-slate-500 text-[11px] mt-0.5">{clientAddress}</p>}
                        </div>
                        <div className="text-right font-mono text-[10px] text-slate-400 space-y-0.5">
                          {clientEmail && <p>{clientEmail}</p>}
                          {clientPhone && <p>📞 {clientPhone}</p>}
                        </div>
                      </div>
                      <table className="w-full border-collapse text-left">
                        <thead>
                          <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase text-[9px]">
                            <th className="py-3">Scope Description</th>
                            <th className="py-3 text-center">Matrix Qty</th>
                            <th className="py-3 text-right">Valuation Allocation</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {watchedLineItems.map((item, i) => (
                            <tr key={i} className="text-slate-700">
                              <td className="py-3.5 font-bold text-slate-900">{item.description || "Watches"}</td>
                              <td className="py-3.5 text-center font-mono text-slate-400">{item.quantity} {item.unit_of_measure !== 1 && `(× ${item.unit_of_measure})`}</td>
                              <td className="py-3.5 text-right font-bold text-indigo-600">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencyToken)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                  <div className="p-8 bg-slate-50 border-t border-slate-100 flex justify-end text-[11px]">
                    <span className="font-mono text-slate-900 font-black">SYSTEM INVOICE STREAM OVERRIDES</span>
                  </div>
                </div>
              )}

              {/* TEMPLATE 5: TECHNICAL BOX */}
              {activeTemplate === "framed" && (
                <div className="bg-white rounded-3xl border-2 border-slate-950 p-6 min-h-[720px] flex flex-col justify-between font-mono text-slate-900 text-xs">
                  <div className="space-y-6">
                    <div className="border-b-2 border-slate-950 pb-4 flex justify-between items-end">
                      <div className="flex items-center gap-2">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-8 h-8 object-cover border border-slate-950" />
                        ) : (
                          <div className="w-8 h-8 bg-slate-950 text-white font-black flex items-center justify-center text-xs">{(company?.name || "T")[0]}</div>
                        )}
                        <div>
                          <div className="text-sm font-black">[INVOICE_LEDGER_RUN]</div>
                          <h3 className="font-bold text-slate-800 text-xs uppercase">{company?.name || "Testing Company"}</h3>
                        </div>
                      </div>
                    </div>
                    <div className="border border-slate-950 rounded-lg overflow-hidden">
                      <div className="bg-slate-100 p-2 font-bold border-b border-slate-950 grid grid-cols-2 text-[10px]">
                        <span>ACCOUNT_SPECIFICATION</span>
                        <span className="text-right">VAL_AGGREGATE</span>
                      </div>
                      {watchedLineItems.map((item, i) => (
                        <div key={i} className="p-2.5 grid grid-cols-2 border-b border-slate-200 last:border-0 bg-white items-center">
                          <span className="font-bold truncate">{item.description || "Trace item data specification…"}</span>
                          <span className="text-right font-bold">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencyToken)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border-t-2 border-slate-950 pt-4 flex justify-between items-center bg-slate-100 p-3 rounded-xl border border-slate-200">
                    <span className="font-black uppercase tracking-wide">ACCOUNT_GRAND_TOTAL:</span>
                    <span className="text-base font-black px-3 py-1 bg-slate-950 text-white rounded-md">{formatCurrency(grandTotal, currencyToken)}</span>
                  </div>
                </div>
              )}

              {/* TEMPLATE 6: CYBER TERMINAL */}
              {activeTemplate === "darkcard" && (
                <div className="bg-slate-950 rounded-3xl border border-slate-800 p-8 min-h-[720px] flex flex-col justify-between font-mono text-emerald-400 text-xs">
                  <div className="space-y-6">
                    <div className="flex justify-between items-start border-b border-slate-800 pb-4">
                      <div className="flex items-center gap-3">
                        {logoPreview ? (
                          <img src={logoPreview} alt="Logo" className="w-10 h-10 border border-emerald-500/20 object-cover rounded" />
                        ) : (
                          <div className="w-10 h-10 border border-emerald-500/30 bg-emerald-500/10 flex items-center justify-center font-black text-white">{(company?.name || "T")[0]}</div>
                        )}
                        <div>
                          <span className="text-slate-500 block text-[10px] font-bold">// FINANCIAL RUNTIME MATRIX CLIENT</span>
                          <h2 className="text-sm font-bold text-white mt-0.5">{company?.name || "Testing Company"}</h2>
                        </div>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {watchedLineItems.map((item, i) => (
                        <div key={i} className="flex justify-between items-center bg-slate-900/40 p-3 rounded-lg border border-slate-900/80 font-mono">
                          <div>
                            <span className="text-white block">{item.description || "Matrix data block mapping…"}</span>
                            <span className="text-[10px] text-slate-500">QUANTITY_ROW: {item.quantity}</span>
                          </div>
                          <span className="text-emerald-300 font-bold">{formatCurrency((item.quantity || 0) * (item.unit_of_measure || 1) * (item.unit_price || 0), currencyToken)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="border-t border-slate-800 pt-4 flex justify-between items-center bg-slate-900/50 p-3 rounded-xl border border-slate-800/80">
                    <span className="text-slate-500 font-bold uppercase tracking-wider">NET_PAYABLE_LIABILITY:</span>
                    <span className="text-base font-bold text-white tracking-tight">{formatCurrency(grandTotal, currencyToken)}</span>
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