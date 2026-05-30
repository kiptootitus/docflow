import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "@/lib/api";
import { Eye, EyeOff } from "lucide-react";
const schema = z.object({
    password: z.string().min(8, "Password must be at least 8 characters long"),
    passwordConfirm: z.string()
}).refine((data) => data.password === data.passwordConfirm, {
    message: "Passwords do not match",
    path: ["passwordConfirm"],
});
export default function ResetPasswordConfirmPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token");
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState("");
    const [showPass, setShowPass] = useState(false);
    const [loading, setLoading] = useState(false);
    const { register, handleSubmit, formState: { errors } } = useForm({
        resolver: zodResolver(schema)
    });
    const onSubmit = async (data) => {
        if (!token) {
            setError("Reset token is missing from the link URL.");
            return;
        }
        setError("");
        setLoading(true);
        try {
            await authApi.confirmPasswordReset(token, data.password);
            setSuccess(true);
        }
        catch (err) {
            setError(err.response?.data?.token?.[0] || err.response?.data?.detail || "Failed to update password.");
        }
        finally {
            setLoading(false);
        }
    };
    if (!token) {
        return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "max-w-md text-center bg-white p-8 rounded-2xl shadow-sm border border-gray-100", children: [_jsx("h2", { className: "text-2xl font-bold text-red-600", children: "\u274C Invalid Reset Link" }), _jsx("p", { className: "mt-4 text-gray-600", children: "This password reset confirmation link is missing its authentication token descriptor." }), _jsx(Link, { to: "/login", className: "mt-6 inline-block text-indigo-600 hover:underline", children: "Back to Login" })] }) }));
    }
    if (success) {
        return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "max-w-md text-center bg-white p-8 rounded-2xl shadow-sm border border-gray-100", children: [_jsx("h2", { className: "text-2xl font-bold text-green-600", children: "\uD83C\uDF89 Password Updated" }), _jsx("p", { className: "mt-4 text-gray-600", children: "Your password has been changed successfully. You can now use your new password to sign in." }), _jsx(Link, { to: "/login", className: "mt-6 inline-block bg-indigo-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-indigo-700", children: "Sign In" })] }) }));
    }
    return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8", children: [_jsx("h1", { className: "text-2xl font-bold text-center text-gray-900", children: "Set New Password" }), _jsx("p", { className: "text-center text-gray-500 mt-2 text-sm", children: "Please choose a strong, secure password containing uppercase, lowercase, numbers, and special characters." }), error && _jsx("div", { className: "bg-red-50 text-red-700 p-3 rounded-lg mt-4 text-sm", children: error }), _jsxs("form", { onSubmit: handleSubmit(onSubmit), className: "mt-6 space-y-4", children: [_jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "New Password" }), _jsxs("div", { className: "relative", children: [_jsx("input", { ...register("password"), type: showPass ? "text" : "password", disabled: loading, placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10" }), _jsx("button", { type: "button", onClick: () => setShowPass(!showPass), className: "absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none", children: showPass ? _jsx(EyeOff, { className: "w-4 h-4" }) : _jsx(Eye, { className: "w-4 h-4" }) })] }), errors.password && _jsx("p", { className: "text-red-500 text-xs mt-1", children: errors.password.message })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Confirm New Password" }), _jsx("input", { ...register("passwordConfirm"), type: "password", disabled: loading, placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" }), errors.passwordConfirm && _jsx("p", { className: "text-red-500 text-xs mt-1", children: errors.passwordConfirm.message })] }), _jsx("button", { type: "submit", disabled: loading, className: "w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50", children: loading ? "Updating Password..." : "Reset Password" })] })] }) }));
}
