import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save } from "lucide-react";
import { companiesApi } from "@/lib/api";
import type { Company } from "@/lib/api";

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = data?.data?.results?.[0];

  const [form, setForm] = useState<Partial<Company>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (company) setForm(company);
  }, [company]);

  const updateMutation = useMutation({
    mutationFn: () => companiesApi.update(company!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["companies"] }); setSaved(true); setTimeout(() => setSaved(false), 2000); },
  });

  const f = (key: keyof Company, label: string, type = "text") => (
    <div>
      <label className="block text-xs font-medium text-gray-600 uppercase tracking-wide mb-1">{label}</label>
      <input type={type} value={(form[key] as string) ?? ""} onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
        className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
    </div>
  );

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <button onClick={() => updateMutation.mutate()} className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Save className="w-4 h-4" /> {saved ? "Saved!" : "Save Changes"}
        </button>
      </div>

      {!company ? <p className="text-gray-500">No company found. Please create one first.</p> : (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            <h2 className="font-semibold text-gray-900 mb-4">Company Information</h2>
            <div className="grid grid-cols-2 gap-4">
              {f("name", "Company Name")}
              {f("email", "Email", "email")}
              {f("phone", "Phone")}
              {f("website", "Website", "url")}
              {f("vat_number", "VAT Number")}
              {f("default_currency", "Default Currency")}
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            <h2 className="font-semibold text-gray-900 mb-4">Address</h2>
            <div className="grid grid-cols-2 gap-4">
              {f("address_line1", "Address Line 1")}
              {f("address_line2", "Address Line 2")}
              {f("city", "City")}
              {f("state", "State / County")}
              {f("postal_code", "Postal Code")}
              {f("country", "Country")}
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-100 p-6">
            <h2 className="font-semibold text-gray-900 mb-4">Invoice Settings</h2>
            <div className="grid grid-cols-2 gap-4">
              {f("invoice_prefix", "Invoice Prefix")}
              {f("payment_due_days", "Payment Due Days", "number")}
              {f("tax_rate", "Default VAT Rate (%)", "number")}
              <div>
                <label className="block text-xs font-medium text-gray-600 uppercase tracking-wide mb-1">Brand Color</label>
                <input type="color" value={(form.branding_color as string) ?? "#6366f1"} onChange={e => setForm(p => ({ ...p, branding_color: e.target.value }))}
                  className="h-10 w-full rounded-lg border border-gray-200 cursor-pointer" />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
