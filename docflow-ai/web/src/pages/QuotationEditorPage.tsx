import { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2, Save, Building2, Phone, User, Globe } from "lucide-react";
import { companiesApi, quotationsApi } from "@/lib/api";

const lineItemSchema = z.object({
  description: z.string().min(1, "Description required"),
  quantity: z.coerce.number().min(1),
  unit_price: z.coerce.number().min(0),
  order: z.number().default(0),
});

const quotationSchema = z.object({
  company: z.string().min(1, "Company required"),
  client: z.string().min(1, "Client required"),
  salutation: z.string().default("Mr."),
  client_phone: z.string().min(1, "Phone number required"),
  building_address: z.string().min(1, "Building address required"),
  currency: z.string().default("KES"),
  issue_date: z.string().min(1),
  due_date: z.string().min(1),
  notes: z.string().optional(),
  terms: z.string().optional(),
  tax_rate: z.coerce.number().default(16),
  discount_amount: z.coerce.number().default(0),
  line_items: z.array(lineItemSchema).min(1, "Add at least one item line"),
});

type QuotationFormValues = z.infer<typeof quotationSchema>;

export default function QuotationEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);
  const aiPrefillData = location.state?.prefill;

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

  const { register, control, handleSubmit, watch, reset, setValue, formState: { errors } } = useForm<QuotationFormValues>({
    resolver: zodResolver(quotationSchema),
    defaultValues: {
      company: company?.id ?? "",
      salutation: "Mr.",
      currency: company?.default_currency ?? "KES",
      issue_date: new Date().toISOString().split("T")[0],
      due_date: new Date(Date.now() + 30 * 86400000).toISOString().split("T")[0],
      tax_rate: 16,
      discount_amount: 0,
      line_items: [{ description: "", quantity: 1, unit_price: 0, order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });
  const watchedItems = watch("line_items") || [];
  const taxRate = watch("tax_rate") || 0;
  const discountAmount = watch("discount_amount") || 0;

  useEffect(() => {
    if (company && !isEditing) {
      setValue("company", company.id);
      setValue("currency", company.default_currency || "KES");
    }
  }, [company, isEditing, setValue]);

  useEffect(() => {
    if (aiPrefillData) {
      if (aiPrefillData.line_items) setValue("line_items", aiPrefillData.line_items);
      if (aiPrefillData.notes) setValue("notes", aiPrefillData.notes);
    }
  }, [aiPrefillData, setValue]);

  useEffect(() => {
    if (quoteData?.data) {
      reset(quoteData.data as any);
    }
  }, [quoteData, reset]);

  const subtotal = watchedItems.reduce((sum, item) => sum + ((item?.quantity || 0) * (item?.unit_price || 0)), 0);
  const taxAmount = subtotal * (taxRate / 100);
  const totalAmount = subtotal + taxAmount - discountAmount;

  // 👇 FIXED: Added missing useMutation pipeline logic back into component
  const saveMutation = useMutation({
    mutationFn: (values: QuotationFormValues) => {
      const payload = {
        ...values,
        subtotal: String(subtotal),
        tax_amount: String(taxAmount),
        total_amount: String(totalAmount),
        number: quoteData?.data?.number ?? `QT-${Math.floor(1000 + Math.random() * 9000)}`,
        status: quoteData?.data?.status ?? "draft",
        line_items: values.line_items.map((item, index) => ({
          ...item,
          order: index,
          unit_price: String(item.unit_price)
        }))
      };
      return isEditing ? quotationsApi.update(id!, payload as any) : quotationsApi.create(payload as any);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quotations"] });
      navigate("/quotations");
    },
    onError: (err: any) => {
      alert(`Failed to save quote: ${err.response?.data?.detail || "Check form parameters."}`);
    }
  });

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto bg-gray-50/50 min-h-screen">
      {/* Header Panel */}
      <div className="flex items-center justify-between gap-4 mb-8 bg-white p-6 rounded-2xl border border-gray-100 shadow-xs">
        <div className="flex items-center gap-4">
          <button type="button" onClick={() => navigate("/quotations")} className="p-2.5 hover:bg-gray-50 text-gray-500 rounded-xl border border-gray-100 transition-all">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 tracking-tight">
              {isEditing ? "Modify Quotation" : "Create New Proposal"}
            </h1>
            <p className="text-gray-400 text-xs sm:text-sm mt-0.5">Draft technical estimates and client structural scope targets.</p>
          </div>
        </div>

        {/* Company Active Branding Icon */}
        <div className="flex items-center gap-3 border-l border-gray-100 pl-6">
          {company?.logo ? (
            <img src={company.logo} alt="Logo" className="w-12 h-12 rounded-xl object-contain border border-gray-100" />
          ) : (
            <div className="w-12 h-12 bg-gradient-to-tr from-indigo-600 to-violet-600 rounded-xl flex items-center justify-center text-white font-black text-lg shadow-sm">
              {company?.name ? company.name[0].toUpperCase() : "D"}
            </div>
          )}
          <div className="hidden sm:block text-left">
            <p className="font-bold text-gray-900 text-sm">{company?.name || "DocFlow Provider"}</p>
            <p className="text-[11px] font-semibold text-indigo-600 tracking-wide uppercase">{company?.city || "Nairobi"}</p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit((data) => saveMutation.mutate(data))} className="space-y-6">
        {/* Client & Metadata Info Card */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-xs space-y-6">
          <h3 className="font-bold text-gray-900 text-sm sm:text-base flex items-center gap-2 pb-3 border-b border-gray-50">
            <User className="w-4 h-4 text-indigo-500" /> Client Profile & Scope Settings
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Salutation</label>
              <select {...register("salutation")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all">
                <option value="Mr.">Mr. (Mister)</option>
                <option value="Mrs.">Mrs. (Mistress)</option>
                <option value="Ms.">Ms. (Miss)</option>
                <option value="Dr.">Dr. (Doctor)</option>
                <option value="Prof.">Prof. (Professor)</option>
              </select>
            </div>

            <div className="sm:col-span-2">
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Target Client Assignee</label>
              <select {...register("client")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all">
                <option value="">Select a customer profile</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              {errors.client && <p className="text-red-500 text-xs mt-1">{errors.client.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                <Phone className="w-3 h-3 text-gray-400" /> Contact Phone Number
              </label>
              <input type="text" {...register("client_phone")} placeholder="e.g. +254 705 830228" className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all bg-white" />
              {errors.client_phone && <p className="text-red-500 text-xs mt-1">{errors.client_phone.message}</p>}
            </div>

            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                <Building2 className="w-3 h-3 text-gray-400" /> Building & Corporate Address
              </label>
              <input type="text" {...register("building_address")} placeholder="e.g. Suite 4B, Delta Towers, Westlands" className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all bg-white" />
              {errors.building_address && <p className="text-red-500 text-xs mt-1">{errors.building_address.message}</p>}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5 flex items-center gap-1">
                <Globe className="w-3 h-3 text-gray-400" /> Currency
              </label>
              <select {...register("currency")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all">
                {["KES", "USD", "EUR", "GBP"].map(curr => <option key={curr} value={curr}>{curr}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Issue Date</label>
              <input type="date" {...register("issue_date")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all bg-white" />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Validity Expiry Date</label>
              <input type="date" {...register("due_date")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all bg-white" />
            </div>
          </div>
        </div>

        {/* Line Items Array */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-xs">
          <h3 className="font-bold text-gray-900 text-sm sm:text-base mb-4 flex items-center gap-2">
            Items Distribution Pricing
          </h3>

          <div className="space-y-3">
            {fields.map((field, index) => (
              <div key={field.id} className="flex flex-col sm:flex-row items-start sm:items-center gap-3 bg-gray-50/50 p-4 rounded-xl border border-gray-100 hover:border-gray-200 transition-all">
                <div className="w-full sm:flex-1">
                  <input {...register(`line_items.${index}.description` as const)} placeholder="Task line item description..." className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" />
                </div>
                <div className="w-full sm:w-24">
                  <input type="number" {...register(`line_items.${index}.quantity` as const)} placeholder="Qty" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all text-center" />
                </div>
                <div className="w-full sm:w-36">
                  <input type="number" step="0.01" {...register(`line_items.${index}.unit_price` as const)} placeholder="Unit Price" className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all text-right" />
                </div>
                {fields.length > 1 && (
                  <button type="button" onClick={() => remove(index)} className="p-2 text-gray-400 hover:text-red-500 rounded-lg self-end sm:self-auto hover:bg-red-50 transition-colors">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <button type="button" onClick={() => append({ description: "", quantity: 1, unit_price: 0, order: fields.length })} className="mt-4 inline-flex items-center gap-2 text-xs font-bold bg-indigo-50 text-indigo-600 hover:bg-indigo-100 px-4 py-2 rounded-xl transition-colors">
            <Plus className="w-3.5 h-3.5" /> Add New Item Breakdown
          </button>
        </div>

        {/* Global summary and adjustments calculation blocks */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 shadow-xs grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">VAT Tax Multiplier (%)</label>
            <input type="number" step="0.01" {...register("tax_rate")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none bg-white transition-all" />
          </div>
          <div>
            <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Discount Value Deduction Amount</label>
            <input type="number" step="0.01" {...register("discount_amount")} className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none bg-white transition-all" />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wide mb-1.5">Proposal Terms & Custom Conditions Notes</label>
            <textarea {...register("notes")} rows={3} placeholder="Add payment milestones or terms validation statements..." className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none bg-white resize-none transition-all" />
          </div>
        </div>

        {/* Submission Bottom Actions Bar */}
        <div className="bg-gradient-to-r from-gray-900 to-slate-800 rounded-2xl p-6 text-white flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 shadow-md">
          <div>
            <p className="text-xs text-slate-400 font-semibold tracking-wide uppercase">Calculated Proposal Value</p>
            <h2 className="text-2xl sm:text-3xl font-black text-indigo-400 tracking-tight mt-0.5">
              {watch("currency")} {totalAmount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </h2>
          </div>
          <button type="submit" disabled={saveMutation.isPending} className="w-full sm:w-auto flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-6 py-3.5 rounded-xl transition-all disabled:opacity-50 shadow-sm active:scale-98">
            <Save className="w-4 h-4" /> {saveMutation.isPending ? "Saving Proposal Data..." : "Save Proposal Quotation"}
          </button>
        </div>
      </form>
    </div>
  );
}