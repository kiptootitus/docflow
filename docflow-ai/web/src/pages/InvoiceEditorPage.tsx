import { useState, useEffect, useCallback } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, GripVertical, Send, Download, ArrowLeft, Eye } from "lucide-react";
import { invoicesApi, companiesApi } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";

const lineItemSchema = z.object({
  description: z.string().min(1, "Description required"),
  quantity: z.coerce.number().min(0.01),
  unit_price: z.coerce.number().min(0),
  order: z.number().default(0),
});

const invoiceSchema = z.object({
  company: z.string().min(1, "Company required"),
  client: z.string().optional(),
  currency: z.string().default("KES"),
  issue_date: z.string().min(1),
  due_date: z.string().optional(),
  notes: z.string().optional(),
  terms: z.string().optional(),
  tax_rate: z.coerce.number().default(16),
  discount_amount: z.coerce.number().default(0),
  line_items: z.array(lineItemSchema).min(1, "Add at least one line item"),
});

type InvoiceForm = z.infer<typeof invoiceSchema>;

export default function InvoiceEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEditing = Boolean(id);

  const { data: companiesData } = useQuery({
    queryKey: ["companies"],
    queryFn: () => companiesApi.list(),
  });
  const company = companiesData?.data?.results?.[0];

  const { data: clientsData } = useQuery({
    queryKey: ["clients"],
    queryFn: () => companiesApi.clients.list(),
    enabled: Boolean(company),
  });
  const clients = clientsData?.data?.results ?? [];

  const { data: invoiceData } = useQuery({
    queryKey: ["invoice", id],
    queryFn: () => invoicesApi.get(id!),
    enabled: isEditing,
  });

  const {
    register,
    control,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<InvoiceForm>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: {
      company: company?.id ?? "",
      currency: company?.default_currency ?? "KES",
      issue_date: new Date().toISOString().split("T")[0],
      due_date: new Date(Date.now() + (company?.payment_due_days ?? 30) * 86400000).toISOString().split("T")[0],
      tax_rate: parseFloat(company?.tax_rate ?? "16"),
      discount_amount: 0,
      line_items: [{ description: "", quantity: 1, unit_price: 0, order: 0 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "line_items" });
  const watchedItems = watch("line_items");
  const taxRate = watch("tax_rate");
  const discount = watch("discount_amount");
  const currency = watch("currency");

  useEffect(() => {
    if (invoiceData?.data) {
      const inv = invoiceData.data;
      reset({
        company: inv.company,
        client: inv.client ?? "",
        currency: inv.currency,
        issue_date: inv.issue_date,
        due_date: inv.due_date ?? "",
        notes: inv.notes,
        terms: inv.terms,
        tax_rate: parseFloat(inv.tax_rate),
        discount_amount: parseFloat(inv.discount_amount),
        line_items: inv.line_items.map((li) => ({
          description: li.description,
          quantity: li.quantity,
          unit_price: parseFloat(li.unit_price),
          order: li.order,
        })),
      });
    }
  }, [invoiceData, reset]);

  useEffect(() => {
    if (company && !isEditing) {
      reset((prev) => ({
        ...prev,
        company: company.id,
        currency: company.default_currency,
        tax_rate: parseFloat(company.tax_rate),
      }));
    }
  }, [company, isEditing, reset]);

  const subtotal = watchedItems.reduce((sum, item) => sum + (item.quantity || 0) * (item.unit_price || 0), 0);
  const taxAmount = subtotal * ((taxRate || 0) / 100);
  const total = subtotal + taxAmount - (discount || 0);

  const createMutation = useMutation({
    mutationFn: (data: InvoiceForm) => invoicesApi.create(data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      navigate(`/invoices/${res.data.id}/edit`);
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: InvoiceForm) => invoicesApi.update(id!, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invoices"] }),
  });

  const sendMutation = useMutation({
    mutationFn: () => invoicesApi.sendEmail(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["invoice", id] }),
  });

  const pdfMutation = useMutation({
    mutationFn: () => invoicesApi.generatePdf(id!),
  });

  const onSubmit = (data: InvoiceForm) => {
    const payload = { ...data, line_items: data.line_items.map((li, i) => ({ ...li, order: i })) };
    if (isEditing) updateMutation.mutate(payload);
    else createMutation.mutate(payload);
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-gray-100 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate("/invoices")} className="text-gray-400 hover:text-gray-600">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">
              {isEditing ? `Edit Invoice` : "New Invoice"}
            </h1>
            {invoiceData?.data && (
              <p className="text-sm text-gray-500">{invoiceData.data.number}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isEditing && (
            <>
              <button
                onClick={() => pdfMutation.mutate()}
                disabled={pdfMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <Download className="w-4 h-4" />
                {pdfMutation.isPending ? "Generating…" : "Generate PDF"}
              </button>
              <button
                onClick={() => sendMutation.mutate()}
                disabled={sendMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                <Send className="w-4 h-4" />
                {sendMutation.isPending ? "Sending…" : "Send to Client"}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="flex h-full">
            {/* Left: Editor */}
            <div className="flex-1 p-8 overflow-auto max-w-2xl">
              <div className="space-y-6">
                {/* Basic Info */}
                <div className="bg-white rounded-xl border border-gray-100 p-6">
                  <h2 className="font-semibold text-gray-900 mb-4">Invoice Details</h2>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Client</label>
                      <select {...register("client")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        <option value="">No client</option>
                        {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Currency</label>
                      <select {...register("currency")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        {["KES","USD","EUR","GBP","ZAR","NGN"].map(c => <option key={c}>{c}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Issue Date</label>
                      <input type="date" {...register("issue_date")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Due Date</label>
                      <input type="date" {...register("due_date")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    </div>
                  </div>
                </div>

                {/* Line Items */}
                <div className="bg-white rounded-xl border border-gray-100 p-6">
                  <h2 className="font-semibold text-gray-900 mb-4">Line Items</h2>
                  <div className="space-y-3">
                    <div className="grid grid-cols-12 gap-2 text-xs font-medium text-gray-500 uppercase tracking-wide px-2">
                      <div className="col-span-5">Description</div>
                      <div className="col-span-2 text-center">Qty</div>
                      <div className="col-span-3 text-right">Unit Price</div>
                      <div className="col-span-2 text-right">Amount</div>
                    </div>
                    {fields.map((field, index) => {
                      const amount = (watchedItems[index]?.quantity || 0) * (watchedItems[index]?.unit_price || 0);
                      return (
                        <div key={field.id} className="grid grid-cols-12 gap-2 items-center bg-gray-50 rounded-lg p-2">
                          <div className="col-span-5">
                            <input
                              {...register(`line_items.${index}.description`)}
                              placeholder="Service or product description"
                              className="w-full bg-transparent border-0 text-sm focus:outline-none text-gray-900"
                            />
                          </div>
                          <div className="col-span-2">
                            <input
                              {...register(`line_items.${index}.quantity`)}
                              type="number"
                              step="0.01"
                              min="0"
                              className="w-full bg-transparent border-0 text-sm text-center focus:outline-none"
                            />
                          </div>
                          <div className="col-span-3">
                            <input
                              {...register(`line_items.${index}.unit_price`)}
                              type="number"
                              step="0.01"
                              min="0"
                              className="w-full bg-transparent border-0 text-sm text-right focus:outline-none"
                            />
                          </div>
                          <div className="col-span-1 text-right text-sm font-medium text-gray-900">
                            {amount.toFixed(2)}
                          </div>
                          <div className="col-span-1 flex justify-end">
                            <button type="button" onClick={() => remove(index)} className="text-gray-300 hover:text-red-400 transition-colors">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                    <button
                      type="button"
                      onClick={() => append({ description: "", quantity: 1, unit_price: 0, order: fields.length })}
                      className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 font-medium pt-1"
                    >
                      <Plus className="w-4 h-4" /> Add Item
                    </button>
                    {errors.line_items && <p className="text-red-500 text-xs">{errors.line_items.message}</p>}
                  </div>
                </div>

                {/* Tax, Discount, Notes */}
                <div className="bg-white rounded-xl border border-gray-100 p-6 grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">VAT Rate (%)</label>
                    <input type="number" step="0.01" {...register("tax_rate")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Discount</label>
                    <input type="number" step="0.01" {...register("discount_amount")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Notes</label>
                    <textarea {...register("notes")} rows={2} placeholder="Payment instructions, thank you note…" className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs font-medium text-gray-600 uppercase tracking-wide">Terms</label>
                    <textarea {...register("terms")} rows={2} placeholder="Payment terms and conditions…" className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="w-full bg-indigo-600 text-white py-3 rounded-xl font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50"
                >
                  {createMutation.isPending || updateMutation.isPending ? "Saving…" : isEditing ? "Save Changes" : "Create Invoice"}
                </button>
              </div>
            </div>

            {/* Right: Live Preview */}
            <div className="w-96 bg-gray-100 border-l border-gray-200 p-6 overflow-auto">
              <div className="flex items-center gap-2 mb-4">
                <Eye className="w-4 h-4 text-gray-500" />
                <h3 className="text-sm font-semibold text-gray-700">Live Preview</h3>
              </div>
              <div className="bg-white rounded-xl shadow-sm p-6 text-xs">
                {/* Preview Header */}
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <p className="font-bold text-base text-gray-900">{company?.name ?? "Your Company"}</p>
                    <p className="text-gray-500 mt-0.5">{company?.address_line1}</p>
                    <p className="text-gray-500">{company?.city}, {company?.country}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-lg text-indigo-600">INVOICE</p>
                    <p className="text-gray-400">{invoiceData?.data?.number ?? "INV-XXXX"}</p>
                  </div>
                </div>

                {/* Line items preview */}
                <table className="w-full mb-4">
                  <thead>
                    <tr className="bg-indigo-600 text-white">
                      <th className="p-2 text-left rounded-tl">Description</th>
                      <th className="p-2 text-center">Qty</th>
                      <th className="p-2 text-right rounded-tr">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {watchedItems.map((item, i) => (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="p-2 text-gray-700">{item.description || "—"}</td>
                        <td className="p-2 text-center text-gray-600">{item.quantity}</td>
                        <td className="p-2 text-right font-medium">
                          {currency} {((item.quantity || 0) * (item.unit_price || 0)).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Totals */}
                <div className="space-y-1 text-right border-t border-gray-100 pt-3">
                  <div className="flex justify-between"><span className="text-gray-500">Subtotal</span><span>{currency} {subtotal.toFixed(2)}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">VAT ({taxRate}%)</span><span>{currency} {taxAmount.toFixed(2)}</span></div>
                  {(discount || 0) > 0 && <div className="flex justify-between text-red-500"><span>Discount</span><span>-{currency} {Number(discount).toFixed(2)}</span></div>}
                  <div className="flex justify-between font-bold text-sm border-t border-gray-200 pt-2 mt-2">
                    <span>Total Due</span>
                    <span className="text-indigo-600">{currency} {total.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
