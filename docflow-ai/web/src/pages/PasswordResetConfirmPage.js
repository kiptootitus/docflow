import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { authApi } from "@/lib/api";
const schema = z.object({
    new_password: z.string().min(8, "Password must be at least 8 characters long"),
    password_confirm: z.string()
}).refine((data) => data.new_password === data.password_confirm, {
    message: "Passwords do not match",
    path: ["password_confirm"]
});
export default function PasswordResetConfirmPage() {
    const { uid, token } = useParams();
    const navigate = useNavigate();
    const [error, setError] = useState("");
    const [success, setSuccess] = useState(false);
    const { register, handleSubmit, formState: { errors } } = useForm({ resolver: zodResolver(schema) });
    const onSubmit = async (data) => {
        if (!uid || !token)
            return;
        try {
            await authApi.confirmPasswordReset({ uid, token, ...data });
            setSuccess(true);
            setTimeout(() => navigate("/login"), 3000);
        }
        catch {
            setError("This token is invalid or expired.");
        }
    };
    return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "w-full max-w-md bg-white rounded-2xl border border-gray-100 shadow-sm p-8", children: [_jsx("h2", { className: "text-xl font-bold text-gray-900 mb-6", children: "Choose New Password" }), success ? (_jsx("div", { className: "bg-emerald-50 text-emerald-700 text-sm rounded-lg p-4", children: "Password updated successfully! Redirecting you back to login portal..." })) : (_jsxs("form", { onSubmit: handleSubmit(onSubmit), className: "space-y-4", children: [error && _jsx("div", { className: "bg-red-50 text-red-700 text-sm rounded-lg p-3", children: error }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "New Password" }), _jsx("input", { type: "password", ...register("new_password"), className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm" }), errors.new_password && _jsx("p", { className: "text-red-500 text-xs mt-1", children: errors.new_password.message })] }), _jsxs("div", { children: [_jsx("label", { className: "block text-sm font-medium text-gray-700 mb-1", children: "Confirm New Password" }), _jsx("input", { type: "password", ...register("password_confirm"), className: "w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm" }), errors.password_confirm && _jsx("p", { className: "text-red-500 text-xs mt-1", children: errors.password_confirm.message })] }), _jsx("button", { type: "submit", className: "w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700", children: "Update Password" })] }))] }) }));
}
