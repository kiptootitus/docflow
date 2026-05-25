import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, PlusCircle, Building2 } from "lucide-react";
import { companiesApi } from "@/lib/api";
import type { Company } from "@/lib/api";

export default function SettingsPage() {
  const qc = useQueryClient();
  
  // Fetch active company listings
  const { data, isLoading } = useQuery({ 
    queryKey: ["companies"], 
    queryFn: () => companiesApi.list() 
  });
  
  const company = data?.data?.results?.[0];
  const hasNoCompany = !company;

  const [form, setForm] = useState<Partial<Company>>({});
  const [statusText, setStatusText] = useState("");

  // Sync state when company pulls down from backend server tracks
  useEffect(() => {
    if (company) {
      setForm(company);
    } else {
      // Default baseline values for initialization mode
      setForm({
        default_currency: "KES",
        tax_rate: 16,
        payment_due_days: 14,
        branding_color: "#6366f1",
        invoice_prefix: "INV"
      });
    }
  }, [company]);

  // Dual-Action Core Sync Mutation Engine
  const saveMutation = useMutation({
    mutationFn: () => {
      if (company?.id) {
        // Mode 1: Update Existing Profile
        return companiesApi.update(company.id, form);
      } else {
        // Mode 2: On-The-Fly Base Account Instantiation
        return companiesApi.create(form as any);
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
      setStatusText("Configuration Saved Successfully!");
      setTimeout(() => setStatusText(""), 3000);
    },
    onError: (err: any) => {
      alert(`Configuration Sync Failed: ${err.response?.data?.detail || "Verify attributes structure alignment."}`);
    }
  });

  const f = (key: keyof Company, label: string, type = "text") => (
    <div className="space-y-1">
      <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider">{label}</label>
      <input 
        type={type} 
        value={(form[key] as string | number) ?? ""} 
        onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
        className="w-full border border-gray-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 bg-gray-50/30 transition-all font-medium text-gray-800" 
      />
    </div>
  );

  if (isLoading) {
    return (
      <div className="p-8 max-w-2xl text-xs text-gray-400 font-medium animate-pulse">
        Syncing system workspace settings...
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-8 max-w-3xl font-sans antialiased text-gray-800">
      
      {/* Dynamic Status Ribbon Control Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 bg-white p-5 rounded-2xl border border-gray-100 shadow-2xs">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-gray-900 flex items-center gap-2">
            <div className="p-2 bg-indigo-50 rounded-xl text-indigo-600">
              <Building2 className="w-5 h-5" />
            </div>
            {hasNoCompany ? "Setup Your Work Profile" : "Application Settings"}
          </h1>
          <p className="text-gray-400 text-xs mt-0.5">
            {hasNoCompany 
              ? "Instantiate your primary company metrics to configure base templates defaults layout parameters." 
              : "Manage transaction variables codes, branding components rules sheets and physical coordinates maps."}
          </p>
        </div>

        <div className="flex items-center gap-3 self-end sm:self-auto">
          {statusText && (
            <span className="text-xs font-bold text-emerald-600 bg-emerald-50 border border-emerald-100 px-3 py-1.5 rounded-xl animate-fade-in">
              {statusText}
            </span>
          )}
          
          <button 
            type="button"
            onClick={() => saveMutation.mutate()} 
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-4 py-2.5 rounded-xl text-xs font-bold transition-all shadow-sm active:scale-98"
          >
            {hasNoCompany ? <PlusCircle className="w-4 h-4" /> : <Save className="w-4 h-4" />} 
            {saveMutation.isPending ? "Syncing..." : hasNoCompany ? "Create Workspace Profile" : "Save Configurations Updates"}
          </button>
        </div>
      </div>

      <div className="space-y-6">
        
        {/* SECTION 1: SYSTEM ENTITY INFORMATION */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5 sm:p-6 shadow-2xs space-y-4">
          <h2 className="font-bold text-xs text-gray-900 uppercase tracking-widest border-b border-gray-50 pb-2">Company Identifiers</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {f("name", "Company Legal Identity Name")}
            {f("email", "Corporate Communications Email", "email")}
            {f("phone", "Contact Phone Link Coordinate")}
            {f("website", "Public Web Address Domain", "url")}
            {f("vat_number", "Tax Registration / VAT Identifier Code")}
            {f("default_currency", "Primary Transaction Valuation Currency")}
          </div>
        </div>

        {/* SECTION 2: PHYSICAL COORDINATES LAYOUT */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5 sm:p-6 shadow-2xs space-y-4">
          <h2 className="font-bold text-xs text-gray-900 uppercase tracking-widest border-b border-gray-50 pb-2">Physical Address Coordinates</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {f("address_line1", "Street Address / Box Suite Line 1")}
            {f("address_line2", "Apartment / Floor Suite Details Line 2")}
            {f("city", "City Hub")}
            {f("state", "State / County Boundary Profile")}
            {f("postal_code", "Postal / Zip Index Code")}
            {f("country", "Sovereign Country Territory Domain")}
          </div>
        </div>

        {/* SECTION 3: AUTOMATED TRANSACTIONS SYSTEM CONFIGURATIONS */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5 sm:p-6 shadow-2xs space-y-4">
          <h2 className="font-bold text-xs text-gray-900 uppercase tracking-widest border-b border-gray-50 pb-2">Default Transaction Rules Variables</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {f("invoice_prefix", "Default Serial Prefix String (e.g. INV, QT)")}
            {f("payment_due_days", "Standard Settlement Grace Frame (Days)", "number")}
            {f("tax_rate", "Default Baseline Local VAT Rate (%)", "number")}
            
            <div className="space-y-1">
              <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider">Document Identity Branding Color</label>
              <div className="flex items-center gap-2">
                <input 
                  type="color" 
                  value={(form.branding_color as string) ?? "#6366f1"} 
                  onChange={e => setForm(p => ({ ...p, branding_color: e.target.value }))}
                  className="h-9 w-16 rounded-xl border border-gray-200 cursor-pointer p-0.5 bg-white" 
                />
                <span className="font-mono text-xs uppercase tracking-wider text-gray-400 font-bold">
                  {(form.branding_color as string) ?? "#6366f1"}
                </span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}