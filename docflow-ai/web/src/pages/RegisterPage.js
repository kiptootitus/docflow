import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Eye, EyeOff } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
export default function RegisterPage() {
    const { setTokens, fetchMe } = useAuthStore();
    const navigate = useNavigate();
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    // Input tracking
    const [form, setForm] = useState({
        email: "",
        first_name: "",
        last_name: "",
        password: "",
        password_confirm: ""
    });
    // Independent toggle states for password fields
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const handleSubmit = async (e) => {
        e.preventDefault();
        if (form.password !== form.password_confirm) {
            setError("Passwords do not match.");
            return;
        }
        setLoading(true);
        setError("");
        try {
            const { data } = await authApi.register(form);
            setTokens(data.tokens.access, data.tokens.refresh);
            await fetchMe();
            navigate("/dashboard");
        }
        catch (err) {
            if (err.response?.data) {
                const backendErrors = err.response.data;
                // Checks if backend returned specific field array validation strings
                if (backendErrors.email) {
                    setError(`Email field: ${backendErrors.email[0]}`);
                }
                else if (backendErrors.password) {
                    setError(`Password field: ${backendErrors.password[0]}`);
                }
                else if (backendErrors.non_field_errors) {
                    setError(backendErrors.non_field_errors[0]);
                }
                else if (typeof backendErrors === "object") {
                    const firstKey = Object.keys(backendErrors)[0];
                    const firstMsg = backendErrors[firstKey];
                    setError(`${firstKey}: ${Array.isArray(firstMsg) ? firstMsg[0] : firstMsg}`);
                }
                else {
                    setError("Registration failed. Please check your network connection.");
                }
            }
            else {
                setError("Registration failed due to a system network error.");
            }
        }
        finally {
            setLoading(false);
        }
    };
    const handleInputChange = (key, value) => {
        setForm(p => ({ ...p, [key]: value }));
    };
    return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "w-full max-w-md", children: [_jsxs("div", { className: "text-center mb-8", children: [_jsx("div", { className: "w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-3", children: _jsx(FileText, { className: "w-6 h-6 text-white" }) }), _jsx("h1", { className: "text-2xl font-bold text-gray-900", children: "Create your account" })] }), _jsxs("div", { className: "bg-white rounded-2xl shadow-sm border border-gray-100 p-8", children: [error && (_jsx("div", { className: "bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 mb-4", children: error })), _jsxs("form", { onSubmit: handleSubmit, className: "space-y-4", children: [_jsxs("div", { className: "grid grid-cols-2 gap-3", children: [_jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "First Name" }), _jsx("input", { type: "text", value: form.first_name, onChange: e => handleInputChange("first_name", e.target.value), className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500", required: true })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Last Name" }), _jsx("input", { type: "text", value: form.last_name, onChange: e => handleInputChange("last_name", e.target.value), className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500", required: true })] })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Email" }), _jsx("input", { type: "email", value: form.email, onChange: e => handleInputChange("email", e.target.value), className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500", required: true })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Password" }), _jsxs("div", { className: "relative", children: [_jsx("input", { type: showPassword ? "text" : "password", value: form.password, onChange: e => handleInputChange("password", e.target.value), placeholder: "At least 8 characters", className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10", required: true }), _jsx("button", { type: "button", onClick: () => setShowPassword(!showPassword), className: "absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none", children: showPassword ? _jsx(EyeOff, { className: "w-4 h-4" }) : _jsx(Eye, { className: "w-4 h-4" }) })] })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Confirm Password" }), _jsxs("div", { className: "relative", children: [_jsx("input", { type: showConfirmPassword ? "text" : "password", value: form.password_confirm, onChange: e => handleInputChange("password_confirm", e.target.value), placeholder: "Repeat your password", className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10", required: true }), _jsx("button", { type: "button", onClick: () => setShowConfirmPassword(!showConfirmPassword), className: "absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none", children: showConfirmPassword ? _jsx(EyeOff, { className: "w-4 h-4" }) : _jsx(Eye, { className: "w-4 h-4" }) })] })] }), _jsx("button", { type: "submit", disabled: loading, className: "w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 mt-2", children: loading ? "Creating account…" : "Create Account" })] }), _jsxs("p", { className: "text-center text-sm text-gray-500 mt-6", children: ["Already have an account?", " ", _jsx(Link, { to: "/login", className: "text-indigo-600 font-medium hover:underline", children: "Sign in" })] })] })] }) }));
}
