import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { authApi } from "@/lib/api";
const schema = z.object({ email: z.string().email("Invalid email address") });
export default function ForgotPassword() {
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState("");
    const { register, handleSubmit, formState: { errors } } = useForm({
        resolver: zodResolver(schema)
    });
    const onSubmit = async (data) => {
        setError("");
        try {
            await authApi.requestPasswordReset(data.email);
            setSuccess(true);
        }
        catch (err) {
            setError(err.response?.data?.detail || "Failed to send reset link.");
        }
    };
    if (success) {
        return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "max-w-md text-center bg-white p-8 rounded-2xl shadow-sm", children: [_jsx("h2", { className: "text-2xl font-bold text-green-600", children: "\u2705 Check Your Email" }), _jsx("p", { className: "mt-4 text-gray-600", children: "We've sent a password reset link." }), _jsx(Link, { to: "/login", className: "mt-6 inline-block text-indigo-600 hover:underline", children: "Back to Login" })] }) }));
    }
    return (_jsx("div", { className: "min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4", children: _jsxs("div", { className: "w-full max-w-md bg-white rounded-2xl shadow-sm p-8", children: [_jsx("h1", { className: "text-2xl font-bold text-center", children: "Forgot Password?" }), _jsx("p", { className: "text-center text-gray-500 mt-2", children: "Enter your email to receive a reset link." }), error && _jsx("div", { className: "bg-red-50 text-red-700 p-3 rounded-lg mt-4", children: error }), _jsxs("form", { onSubmit: handleSubmit(onSubmit), className: "mt-6 space-y-4", children: [_jsx("input", { ...register("email"), type: "email", placeholder: "you@company.com", className: "w-full border border-gray-200 rounded-lg px-4 py-3 focus:ring-2 focus:ring-indigo-500" }), errors.email && _jsx("p", { className: "text-red-500 text-sm", children: errors.email.message }), _jsx("button", { type: "submit", className: "w-full bg-indigo-600 text-white py-3 rounded-lg font-medium hover:bg-indigo-700", children: "Send Reset Link" })] }), _jsx("p", { className: "text-center mt-6 text-sm", children: _jsx(Link, { to: "/login", className: "text-indigo-600 hover:underline", children: "Back to Login" }) })] }) }));
}
