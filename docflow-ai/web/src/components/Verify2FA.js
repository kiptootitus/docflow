import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
export default function Verify2FA() {
    const [code, setCode] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const location = useLocation();
    const navigate = useNavigate();
    const { handleLoginSuccess } = useAuthStore();
    // Pull target identifier forwarded during core validation stage
    const email = location.state?.email;
    const handleVerify = async () => {
        if (!email) {
            setError("Authentication session lost. Please log in again.");
            return;
        }
        setError("");
        setLoading(true);
        try {
            // Direct integration with the new backend flow
            const response = await authApi.verifyTOTPLogin(email, code);
            // Load user profiles seamlessly into client storage memory
            await handleLoginSuccess(response.data.access, response.data.refresh);
            navigate("/dashboard");
        }
        catch (err) {
            setError(err.response?.data?.token?.[0] || err.response?.data?.detail || "Invalid code. Please try again.");
        }
        finally {
            setLoading(false);
        }
    };
    return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center", children: _jsxs("div", { className: "bg-white p-8 rounded-2xl shadow-sm w-full max-w-md", children: [_jsx("h2", { className: "text-2xl font-bold text-center", children: "Two-Factor Authentication" }), _jsx("p", { className: "text-center text-gray-500 mt-2", children: "Enter the code from your authenticator app" }), error && _jsx("div", { className: "bg-red-50 text-red-700 p-3 rounded mt-4 text-sm", children: error }), _jsx("input", { type: "text", maxLength: 6, value: code, disabled: loading || !email, onChange: (e) => setCode(e.target.value.replace(/\D/g, "")), className: "w-full text-center text-4xl tracking-widest border border-gray-200 rounded-lg py-4 mt-6 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50", placeholder: "123456" }), _jsx("button", { onClick: handleVerify, disabled: loading || code.length !== 6 || !email, className: "w-full bg-indigo-600 text-white py-3 rounded-lg mt-6 font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors", children: loading ? "Verifying..." : "Verify" }), _jsxs("p", { className: "text-center text-sm text-gray-500 mt-6", children: ["Lost access? Use a ", _jsx("button", { type: "button", className: "text-indigo-600 font-medium hover:underline", children: "backup code" })] })] }) }));
}
