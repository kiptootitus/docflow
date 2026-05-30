import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Shield, QrCode, Copy, Check } from "lucide-react";
import { companiesApi, authApi } from "@/lib/api";
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
    const [form, setForm] = useState({});
    const [statusText, setStatusText] = useState("");
    const [show2FASection, setShow2FASection] = useState(false);
    const [qrCode, setQrCode] = useState("");
    const [secret, setSecret] = useState("");
    const [backupCodes, setBackupCodes] = useState([]);
    const [copied, setCopied] = useState(false);
    const [verificationCode, setVerificationCode] = useState("");
    const [verifying, setVerifying] = useState(false);
    // Fetch Company
    useEffect(() => {
        if (company) {
            setForm(company);
        }
        else {
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
            }
            else {
                return companiesApi.create(form);
            }
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ["companies"] });
            setStatusText("Company settings saved successfully!");
            setTimeout(() => setStatusText(""), 3000);
        },
        onError: (err) => {
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
        onError: (err) => {
            alert(`Failed to enable 2FA: ${err.response?.data?.detail || "Try again."}`);
        }
    });
    // Verify 2FA Code
    const verify2FAMutation = useMutation({
        mutationFn: (code) => authApi.verify2FA(code),
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
        }
        catch (err) {
            console.error("Failed to load backup codes");
        }
    };
    const copyToClipboard = (text) => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };
    const f = (key, label, type = "text") => (_jsxs("div", { className: "space-y-1", children: [_jsx("label", { className: "block text-[10px] font-bold text-gray-500 uppercase tracking-wider", children: label }), _jsx("input", { type: type, value: form[key] ?? "", onChange: e => setForm(p => ({ ...p, [key]: e.target.value })), className: "w-full border border-gray-200 rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 bg-gray-50/30 transition-all font-medium text-gray-800" })] }));
    if (companyLoading) {
        return _jsx("div", { className: "p-8 text-xs text-gray-400 animate-pulse", children: "Loading settings..." });
    }
    return (_jsxs("div", { className: "p-4 sm:p-8 max-w-4xl font-sans antialiased text-gray-800", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8 bg-white p-6 rounded-2xl border border-gray-100 shadow-sm", children: [_jsxs("div", { children: [_jsxs("h1", { className: "text-2xl font-bold tracking-tight text-gray-900 flex items-center gap-3", children: [_jsx("div", { className: "p-3 bg-indigo-50 rounded-2xl text-indigo-600", children: _jsx(Building2, { className: "w-6 h-6" }) }), "Account & Security Settings"] }), _jsx("p", { className: "text-gray-500 mt-1", children: "Manage your workspace and security preferences" })] }), _jsxs("div", { className: "flex items-center gap-3", children: [statusText && (_jsx("span", { className: "text-sm font-medium text-emerald-600 bg-emerald-50 px-4 py-2 rounded-xl", children: statusText })), _jsx("button", { onClick: () => saveMutation.mutate(), disabled: saveMutation.isPending, className: "flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-all", children: saveMutation.isPending ? "Saving..." : "Save Company Settings" })] })] }), _jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-8", children: [_jsxs("div", { className: "space-y-8", children: [_jsxs("div", { className: "bg-white rounded-3xl border border-gray-100 p-8 shadow-sm", children: [_jsxs("h2", { className: "font-semibold text-lg mb-6 flex items-center gap-2", children: [_jsx(Building2, { className: "w-5 h-5 text-indigo-600" }), "Company Profile"] }), _jsxs("div", { className: "space-y-6", children: [f("name", "Company Legal Name"), f("email", "Business Email", "email"), f("phone", "Phone Number"), f("website", "Website", "url"), f("vat_number", "VAT / Tax ID")] })] }), _jsxs("div", { className: "bg-white rounded-3xl border border-gray-100 p-8 shadow-sm", children: [_jsx("h2", { className: "font-semibold text-lg mb-6", children: "Transaction Defaults" }), _jsxs("div", { className: "space-y-6", children: [f("default_currency", "Default Currency"), f("invoice_prefix", "Invoice Prefix"), f("payment_due_days", "Payment Due Days", "number"), f("tax_rate", "Tax Rate (%)", "number"), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-2", children: "Branding Color" }), _jsxs("div", { className: "flex items-center gap-3", children: [_jsx("input", { type: "color", value: form.branding_color ?? "#6366f1", onChange: e => setForm(p => ({ ...p, branding_color: e.target.value })), className: "h-12 w-20 rounded-xl border border-gray-200 cursor-pointer" }), _jsx("span", { className: "font-mono text-sm text-gray-500", children: form.branding_color ?? "#6366f1" })] })] })] })] })] }), _jsxs("div", { className: "bg-white rounded-3xl border border-gray-100 p-8 shadow-sm h-fit", children: [_jsx("div", { className: "flex items-center justify-between mb-6", children: _jsxs("h2", { className: "font-semibold text-lg flex items-center gap-2", children: [_jsx(Shield, { className: "w-5 h-5 text-indigo-600" }), "Security"] }) }), _jsxs("div", { className: "space-y-6", children: [_jsx("div", { children: _jsxs("div", { className: "flex justify-between items-center", children: [_jsxs("div", { children: [_jsx("p", { className: "font-medium", children: "Two-Factor Authentication (2FA)" }), _jsx("p", { className: "text-sm text-gray-500", children: "Add an extra layer of security" })] }), _jsx("button", { onClick: () => enable2FAMutation.mutate(), disabled: enable2FAMutation.isPending, className: "px-5 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 disabled:opacity-50", children: enable2FAMutation.isPending ? "Enabling..." : "Enable 2FA" })] }) }), show2FASection && qrCode && (_jsxs("div", { className: "border border-indigo-100 bg-indigo-50/50 rounded-2xl p-6", children: [_jsxs("div", { className: "text-center mb-4", children: [_jsx(QrCode, { className: "w-8 h-8 mx-auto text-indigo-600 mb-2" }), _jsx("h3", { className: "font-semibold", children: "Scan QR Code" }), _jsx("p", { className: "text-sm text-gray-600 mt-1", children: "Use Google Authenticator, Authy, or Microsoft Authenticator" })] }), _jsx("div", { className: "flex justify-center mb-6 bg-white p-4 rounded-xl", children: _jsx("img", { src: qrCode, alt: "2FA QR Code", className: "border border-gray-200 rounded-lg" }) }), _jsxs("div", { className: "text-center mb-4", children: [_jsx("p", { className: "text-xs text-gray-500", children: "Or enter this secret manually:" }), _jsx("code", { className: "bg-gray-100 px-3 py-1 rounded font-mono text-sm", children: secret })] }), _jsxs("div", { className: "space-y-3", children: [_jsx("input", { type: "text", maxLength: 6, value: verificationCode, onChange: (e) => setVerificationCode(e.target.value.replace(/\D/g, '')), placeholder: "Enter 6-digit code", className: "w-full text-center text-3xl tracking-widest py-4 border border-gray-200 rounded-2xl focus:ring-2 focus:ring-indigo-500" }), _jsx("button", { onClick: () => verify2FAMutation.mutate(verificationCode), disabled: verifying || verificationCode.length !== 6, className: "w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-2xl font-medium disabled:opacity-50", children: "Verify & Activate 2FA" })] })] })), backupCodes.length > 0 && (_jsxs("div", { className: "mt-8", children: [_jsxs("h3", { className: "font-medium mb-3 flex items-center gap-2", children: ["Backup Codes", _jsx("span", { className: "text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded", children: "One-time use" })] }), _jsx("div", { className: "grid grid-cols-2 gap-2 bg-gray-50 p-4 rounded-2xl", children: backupCodes.map((code, i) => (_jsxs("div", { className: "font-mono text-sm bg-white border border-gray-100 p-3 rounded-lg flex justify-between items-center", children: [code, _jsx("button", { onClick: () => copyToClipboard(code), children: copied ? _jsx(Check, { className: "w-4 h-4 text-green-500" }) : _jsx(Copy, { className: "w-4 h-4 text-gray-400" }) })] }, i))) }), _jsx("p", { className: "text-xs text-gray-500 mt-3", children: "Save these codes somewhere safe. They can be used if you lose access to your authenticator." })] }))] })] })] })] }));
}
