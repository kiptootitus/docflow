import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Save, PlusCircle, Building2, Shield, QrCode, Copy, Check } from "lucide-react";
import { companiesApi, authApi } from "@/lib/api";
import type { Company } from "@/lib/api";

export default function SettingsPage() {
  const qc = useQueryClient();

  // Company Settings
  const { data, isLoading: companyLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => companiesApi.list()
  });

  const company = data?.data?.results?.[0];
  const hasNoCompany = !company;

  // 2FA States
  const [form, setForm] = useState<Partial<Company>>({});
  const [statusText, setStatusText] = useState("");
  const [show2FASection, setShow2FASection] = useState(false);
  const [qrCode, setQrCode] = useState<string>("");
  const [secret, setSecret] = useState<string>("");
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [verificationCode, setVerificationCode] = useState("");
  const [verifying, setVerifying] = useState(false);

  // Fetch Company
  useEffect(() => {
    if (company) {
      setForm(company);
    } else {
      setForm({
        default_currency: "KES",
        tax_rate: 16,
        payment_due_days: 14,
        branding_color: "#6366f1",
        invoice_prefix: "INV"
      });
    }
  }, [company]);

  // Save Company Settings
  const saveMutation = useMutation({
    mutationFn: () => {
      if (company?.id) {
        return companiesApi.update(company.id, form);
      } else {
        return companiesApi.create(form as any);
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
      setStatusText("Company settings saved successfully!");
      setTimeout(() => setStatusText(""), 3000);
    },
    onError: (err: any) => {
      alert(`Save failed: ${err.response?.data?.detail || "Please check your input."}`);
    }
  });

  // Enable 2FA Mutation
  const enable2FAMutation = useMutation({
    mutationFn: () => authApi.enable2FA(),
    onSuccess: (res) => {
      setQrCode(res.data.qr_code);
      setSecret(res.data.secret);
      setShow2FASection(true);
    },
    onError: (err: any) => {
      alert(`Failed to enable 2FA: ${err.response?.data?.detail || "Try again."}`);
    }
  });

  // Verify 2FA Code
  const verify2FAMutation = useMutation({
    mutationFn: (code: string) => authApi.verify2FA(code),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["user"] });
      setStatusText("✅ Two-Factor Authentication enabled successfully!");
      setVerificationCode("");
      setShow2FASection(false);
      // Refresh backup codes
      loadBackupCodes();
    },
    onError: () => {
      alert("Invalid code. Please try again.");
    }
  });

  // Load Backup Codes
  const loadBackupCodes = async () => {
    try {
      const res = await authApi.getBackupCodes();
      setBackupCodes(res.data.backup_codes || []);
    } catch (err) {
      console.error("Failed to load backup codes");
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

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

  if (companyLoading) {
    return <div className="p-8 text-xs text-gray-400 animate-pulse">Loading settings...</div>;
  }

  return (
    <div className="p-4 sm:p-8 max-w-4xl font-sans antialiased text-gray-800">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 flex items-center gap-3">
            <div className="p-3 bg-indigo-50 rounded-2xl text-indigo-600">
              <Building2 className="w-6 h-6" />
            </div>
            Account & Security Settings
          </h1>
          <p className="text-gray-500 mt-1">Manage your workspace and security preferences</p>
        </div>

        <div className="flex items-center gap-3">
          {statusText && (
            <span className="text-sm font-medium text-emerald-600 bg-emerald-50 px-4 py-2 rounded-xl">
              {statusText}
            </span>
          )}
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-all"
          >
            {saveMutation.isPending ? "Saving..." : "Save Company Settings"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Company Information */}
        <div className="space-y-8">
          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <h2 className="font-semibold text-lg mb-6 flex items-center gap-2">
              <Building2 className="w-5 h-5 text-indigo-600" />
              Company Profile
            </h2>
            <div className="space-y-6">
              {f("name", "Company Legal Name")}
              {f("email", "Business Email", "email")}
              {f("phone", "Phone Number")}
              {f("website", "Website", "url")}
              {f("vat_number", "VAT / Tax ID")}
            </div>
          </div>

          <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm">
            <h2 className="font-semibold text-lg mb-6">Transaction Defaults</h2>
            <div className="space-y-6">
              {f("default_currency", "Default Currency")}
              {f("invoice_prefix", "Invoice Prefix")}
              {f("payment_due_days", "Payment Due Days", "number")}
              {f("tax_rate", "Tax Rate (%)", "number")}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Branding Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={(form.branding_color as string) ?? "#6366f1"}
                    onChange={e => setForm(p => ({ ...p, branding_color: e.target.value }))}
                    className="h-12 w-20 rounded-xl border border-gray-200 cursor-pointer"
                  />
                  <span className="font-mono text-sm text-gray-500">
                    {(form.branding_color as string) ?? "#6366f1"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Security Section - 2FA */}
        <div className="bg-white rounded-3xl border border-gray-100 p-8 shadow-sm h-fit">
          <div className="flex items-center justify-between mb-6">
            <h2 className="font-semibold text-lg flex items-center gap-2">
              <Shield className="w-5 h-5 text-indigo-600" />
              Security
            </h2>
          </div>

          <div className="space-y-6">
            <div>
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium">Two-Factor Authentication (2FA)</p>
                  <p className="text-sm text-gray-500">Add an extra layer of security</p>
                </div>
                <button
                  onClick={() => enable2FAMutation.mutate()}
                  disabled={enable2FAMutation.isPending}
                  className="px-5 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 disabled:opacity-50"
                >
                  {enable2FAMutation.isPending ? "Enabling..." : "Enable 2FA"}
                </button>
              </div>
            </div>

            {/* 2FA Setup Modal Section */}
            {show2FASection && qrCode && (
              <div className="border border-indigo-100 bg-indigo-50/50 rounded-2xl p-6">
                <div className="text-center mb-4">
                  <QrCode className="w-8 h-8 mx-auto text-indigo-600 mb-2" />
                  <h3 className="font-semibold">Scan QR Code</h3>
                  <p className="text-sm text-gray-600 mt-1">Use Google Authenticator, Authy, or Microsoft Authenticator</p>
                </div>

                <div className="flex justify-center mb-6 bg-white p-4 rounded-xl">
                  <img src={qrCode} alt="2FA QR Code" className="border border-gray-200 rounded-lg" />
                </div>

                <div className="text-center mb-4">
                  <p className="text-xs text-gray-500">Or enter this secret manually:</p>
                  <code className="bg-gray-100 px-3 py-1 rounded font-mono text-sm">{secret}</code>
                </div>

                <div className="space-y-3">
                  <input
                    type="text"
                    maxLength={6}
                    value={verificationCode}
                    onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="Enter 6-digit code"
                    className="w-full text-center text-3xl tracking-widest py-4 border border-gray-200 rounded-2xl focus:ring-2 focus:ring-indigo-500"
                  />

                  <button
                    onClick={() => verify2FAMutation.mutate(verificationCode)}
                    disabled={verifying || verificationCode.length !== 6}
                    className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-2xl font-medium disabled:opacity-50"
                  >
                    Verify & Activate 2FA
                  </button>
                </div>
              </div>
            )}

            {/* Backup Codes */}
            {backupCodes.length > 0 && (
              <div className="mt-8">
                <h3 className="font-medium mb-3 flex items-center gap-2">
                  Backup Codes
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">One-time use</span>
                </h3>
                <div className="grid grid-cols-2 gap-2 bg-gray-50 p-4 rounded-2xl">
                  {backupCodes.map((code, i) => (
                    <div key={i} className="font-mono text-sm bg-white border border-gray-100 p-3 rounded-lg flex justify-between items-center">
                      {code}
                      <button onClick={() => copyToClipboard(code)}>
                        {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-3">Save these codes somewhere safe. They can be used if you lose access to your authenticator.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}