import { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Send, Download, ArrowLeft, Eye } from "lucide-react";
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
  const [showMobilePreview, setShowMobilePreview] = useState(false);

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
    <div className="h-full flex flex-col min-w-0">
      {/* Header */}
      <div className="bg-white border-b border-gray-100 px-4 sm:px-8 py-4 flex flex-col sm:flex-row gap-4 sm:items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate("/invoices")} className="text-gray-400 hover:text-gray-600 p-1">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-base sm:text-lg font-semibold text-gray-900">
              {isEditing ? `Edit Invoice` : "New Invoice"}
            </h1>
            {invoiceData?.data && (
              <p className="text-xs sm:text-sm text-gray-500">{invoiceData.data.number}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <button
            type="button"
            onClick={() => setShowMobilePreview(!showMobilePreview)}
            className="lg:hidden flex items-center justify-center gap-2 px-3 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 bg-white shadow-xs"
          >
            <Eye className="w-4 h-4" />
            {showMobilePreview ? "Show Form" : "Preview"}
          </button>
          {isEditing && (
            <>
              <button
                onClick={() => pdfMutation.mutate()}
                disabled={pdfMutation.isPending}
                className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 sm:px-4 py-2 border border-gray-200 rounded-lg text-xs sm:text-sm font-medium text-gray-700 hover:bg-gray-50 bg-white"
              >
                <Download className="w-4 h-4" />
                {pdfMutation.isPending ? "Generating..." : "PDF"}
              </button>
              <button
                onClick={() => sendMutation.mutate()}
                disabled={sendMutation.isPending}
                className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-3 sm:px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs sm:text-sm font-medium hover:bg-indigo-700"
              >
                <Send className="w-4 h-4" />
                {sendMutation.isPending ? "Sending..." : "Send"}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-hidden bg-gray-50">
        <form onSubmit={handleSubmit(onSubmit)} className="h-full">
          <div className="flex flex-col lg:flex-row h-full w-full">

            {/* Left Frame: Form Fields */}
            <div className={cn(
              "flex-1 p-4 sm:p-8 overflow-y-auto w-full lg:max-w-3xl xl:max-w-4xl mx-auto",
              showMobilePreview ? "hidden lg:block" : "block"
            )}>
              <div className="space-y-6">

                {/* Details Card */}
                <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 shadow-xs">
                  <h2 className="font-semibold text-gray-900 mb-4 text-sm sm:text-base">Invoice Details</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Client</label>
                      <select {...register("client")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        <option value="">No client</option>
                        {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Currency</label>
                      <select {...register("currency")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        {["KES","USD","EUR","GBP","ZAR","NGN"].map(c => <option key={c}>{c}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Issue Date</label>
                      <input type="date" {...register("issue_date")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    </div>
                    <div>
                      <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Due Date</label>
                      <input type="date" {...register("due_date")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    </div>
                  </div>
                </div>

                {/* Line Items Entry Container */}
                <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 shadow-xs">
                  <h2 className="font-semibold text-gray-900 mb-4 text-sm sm:text-base">Line Items</h2>
                  <div className="space-y-4">
                    {/* Desktop Column Header Titles */}
                    <div className="hidden sm:grid grid-cols-12 gap-2 text-[11px] font-semibold text-gray-400 uppercase tracking-wide px-2">
                      <div className="col-span-5">Description</div>
                      <div className="col-span-2 text-center">Qty</div>
                      <div className="col-span-3 text-right">Unit Price</div>
                      <div className="col-span-2 text-right">Total</div>
                    </div>

                    {fields.map((field, index) => {
                      const amount = (watchedItems[index]?.quantity || 0) * (watchedItems[index]?.unit_price || 0);
                      return (
                        <div key={field.id} className="flex flex-col sm:grid sm:grid-cols-12 gap-3 sm:gap-2 items-start sm:items-center bg-gray-50/70 sm:bg-gray-50 rounded-xl p-3 sm:p-2 border border-gray-100 sm:border-none">
                          <div className="w-full col-span-5">
                            <label className="sm:hidden text-[10px] font-bold text-gray-400 uppercase mb-1 block">Description</label>
                            <input
                              {...register(`line_items.${index}.description`)}
                              placeholder="Service or product description"
                              className="w-full bg-white sm:bg-transparent border border-gray-200 sm:border-0 rounded-md sm:rounded-none px-2.5 py-1.5 sm:p-0 text-sm focus:outline-none text-gray-900"
                            />
                          </div>
                          <div className="w-full col-span-2">
                            <label className="sm:hidden text-[10px] font-bold text-gray-400 uppercase mb-1 block">Quantity</label>
                            <input
                              {...register(`line_items.${index}.quantity`)}
                              type="number"
                              step="0.01"
                              min="0"
                              className="w-full bg-white sm:bg-transparent border border-gray-200 sm:border-0 rounded-md sm:rounded-none px-2.5 py-1.5 sm:p-0 text-sm text-left sm:text-center focus:outline-none"
                            />
                          </div>
                          <div className="w-full col-span-3">
                            <label className="sm:hidden text-[10px] font-bold text-gray-400 uppercase mb-1 block">Unit Price</label>
                            <input
                              {...register(`line_items.${index}.unit_price`)}
                              type="number"
                              step="0.01"
                              min="0"
                              className="w-full bg-white sm:bg-transparent border border-gray-200 sm:border-0 rounded-md sm:rounded-none px-2.5 py-1.5 sm:p-0 text-sm text-left sm:text-right focus:outline-none"
                            />
                          </div>

                          <div className="w-full col-span-2 flex items-center justify-between sm:justify-end gap-2 mt-1 sm:mt-0 pt-2 sm:pt-0 border-t border-gray-200 sm:border-none">
                            <div className="sm:hidden text-xs font-semibold text-gray-500">Total:</div>
                            <div className="text-sm font-semibold text-gray-900 pr-1">
                              {amount.toFixed(2)}
                            </div>
                            <button type="button" onClick={() => remove(index)} className="text-gray-400 hover:text-red-500 transition-colors p-1.5 rounded-lg hover:bg-red-50 sm:hover:bg-transparent">
                              <Trash2 className="w-4 h-4 sm:w-3.5 sm:h-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    <button
                      type="button"
                      onClick={() => append({ description: "", quantity: 1, unit_price: 0, order: fields.length })}
                      className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 font-semibold pt-1"
                    >
                      <Plus className="w-4 h-4" /> Add Item
                    </button>
                    {errors.line_items && <p className="text-red-500 text-xs mt-1">{errors.line_items.message}</p>}
                  </div>
                </div>

                {/* Meta Variables Details */}
                <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 grid grid-cols-1 sm:grid-cols-2 gap-4 shadow-xs">
                  <div>
                    <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">VAT Rate (%)</label>
                    <input type="number" step="0.01" {...register("tax_rate")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
                  </div>
                  <div>
                    <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Discount Amount</label>
                    <input type="number" step="0.01" {...register("discount_amount")} className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white" />
                  </div>
                  <div className="col-span-1 sm:col-span-2">
                    <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Notes</label>
                    <textarea {...register("notes")} rows={2} placeholder="Payment instructions, thank you note..." className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none bg-white" />
                  </div>
                  <div className="col-span-1 sm:col-span-2">
                    <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Terms</label>
                    <textarea {...register("terms")} rows={2} placeholder="Payment terms and conditions..." className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none bg-white" />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                  className="w-full bg-indigo-600 text-white py-3 rounded-xl font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-50 shadow-sm text-sm sm:text-base"
                >
                  {createMutation.isPending || updateMutation.isPending ? "Saving..." : isEditing ? "Save Changes" : "Create Invoice"}
                </button>
              </div>
            </div>

            {/* Right Frame: Live View Canvas Panel */}
            <div className={cn(
              "w-full lg:w-96 bg-gray-100/60 lg:border-l border-gray-200 p-4 sm:p-6 overflow-y-auto lg:block flex-shrink-0",
              showMobilePreview ? "block" : "hidden lg:block"
            )}>
              <div className="flex items-center gap-2 mb-4">
                <Eye className="w-4 h-4 text-gray-500" />
                <h3 className="text-sm font-semibold text-gray-700">Live Preview</h3>
              </div>
              <div className="bg-white rounded-xl shadow-sm p-4 sm:p-6 text-[11px] sm:text-xs border border-gray-100">
                {/* Preview Header */}
                <div className="flex flex-col sm:flex-row justify-between items-start gap-4 mb-6">
                  <div className="min-w-0">
                    <p className="font-bold text-sm sm:text-base text-gray-900 truncate">{company?.name ?? "Your Company"}</p>
                    <p className="text-gray-500 mt-0.5 truncate">{company?.address_line1}</p>
                    <p className="text-gray-500 truncate">{company?.city}, {company?.country}</p>
                  </div>
                  <div className="text-left sm:text-right flex-shrink-0">
                    <p className="font-bold text-base sm:text-lg text-indigo-600 tracking-wide">INVOICE</p>
                    <p className="text-gray-400 font-medium">{invoiceData?.data?.number ?? "INV-XXXX"}</p>
                  </div>
                </div>

                {/* Line items table view wrapper */}
                <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
                  <table className="w-full mb-4 table-fixed min-w-[280px]">
                    <thead>
                      <tr className="bg-indigo-600 text-white text-[10px] uppercase tracking-wider">
                        <th className="p-2 text-left rounded-tl w-1/2">Description</th>
                        <th className="p-2 text-center w-1/6">Qty</th>
                        <th className="p-2 text-right rounded-tr w-1/3">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {watchedItems.map((item, i) => (
                        <tr key={i} className="border-b border-gray-50">
                          <td className="p-2 text-gray-700 break-words">{item.description || "—"}</td>
                          <td className="p-2 text-center text-gray-600">{item.quantity}</td>
                          <td className="p-2 text-right font-medium text-gray-900">
                            {currency} {((item.quantity || 0) * (item.unit_price || 0)).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Totals Summary */}
                <div className="space-y-1.5 text-right border-t border-gray-100 pt-3">
                  <div className="flex justify-between text-gray-500"><span>Subtotal</span><span className="font-medium text-gray-900">{currency} {subtotal.toFixed(2)}</span></div>
                  <div className="flex justify-between text-gray-500"><span>VAT ({taxRate}%)</span><span className="font-medium text-gray-900">{currency} {taxAmount.toFixed(2)}</span></div>
                  {(discount || 0) > 0 && <div className="flex justify-between text-red-500 font-medium"><span>Discount</span><span>-{currency} {Number(discount).toFixed(2)}</span></div>}
                  <div className="flex justify-between font-bold text-xs sm:text-sm border-t border-gray-200 pt-2.5 mt-2">
                    <span className="text-gray-900">Total Due</span>
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