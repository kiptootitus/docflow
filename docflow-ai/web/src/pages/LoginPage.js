import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, EyeOff, ArrowRight, Loader2, ShieldCheck } from "lucide-react";
import { useAuthStore } from "@/lib/auth-store";
import { useGoogleLogin } from "@react-oauth/google";
import { authApi } from "@/lib/api";
// ---------------------------------------------------------------------------
// Validation schema
// ---------------------------------------------------------------------------
const schema = z.object({
    email: z.string().email("Please enter a valid email address"),
    password: z.string().min(1, "Password is required"),
});
// ---------------------------------------------------------------------------
// TOTP / 2FA modal
// ---------------------------------------------------------------------------
function TwoFactorModal({ email, onVerified, onCancel, }) {
    const [code, setCode] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const handleVerify = async () => {
        if (code.length !== 6) {
            setError("Enter the 6-digit code from your authenticator app.");
            return;
        }
        setError("");
        setLoading(true);
        try {
            const { data } = await authApi.verifyTotp({ email, token: code });
            onVerified({ access: data.access, refresh: data.refresh });
        }
        catch (err) {
            setError(err.response?.data?.detail ||
                "Invalid or expired code. Please try again.");
        }
        finally {
            setLoading(false);
        }
    };
    return (_jsx("div", { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm", children: _jsxs("div", { className: "bg-[#0f1117] border border-white/10 rounded-2xl p-8 w-full max-w-sm shadow-2xl", children: [_jsxs("div", { className: "flex items-center gap-3 mb-6", children: [_jsx("div", { className: "w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center", children: _jsx(ShieldCheck, { className: "w-5 h-5 text-indigo-400" }) }), _jsxs("div", { children: [_jsx("h2", { className: "text-white font-semibold text-base", children: "Two-Factor Authentication" }), _jsx("p", { className: "text-white/40 text-xs", children: "Enter the code from your authenticator app" })] })] }), error && (_jsx("div", { className: "bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded-lg px-4 py-2.5 mb-4", children: error })), _jsx("input", { type: "text", inputMode: "numeric", maxLength: 6, value: code, onChange: (e) => setCode(e.target.value.replace(/\D/g, "")), placeholder: "000000", className: "w-full text-center text-3xl font-mono tracking-[0.4em] bg-white/5 border border-white/10 rounded-xl px-4 py-4 text-white placeholder:text-white/20 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 mb-5" }), _jsx("button", { onClick: handleVerify, disabled: loading || code.length !== 6, className: "w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium py-3 rounded-xl transition-all duration-200 flex items-center justify-center gap-2 mb-3", children: loading ? (_jsx(Loader2, { className: "w-4 h-4 animate-spin" })) : ("Verify & Sign In") }), _jsx("button", { onClick: onCancel, className: "w-full text-white/40 hover:text-white/70 text-sm py-2 transition-colors", children: "Cancel" })] }) }));
}
// ---------------------------------------------------------------------------
// Main LoginPage
// ---------------------------------------------------------------------------
export default function LoginPage() {
    const { login, handleLoginSuccess } = useAuthStore();
    const navigate = useNavigate();
    const [showPass, setShowPass] = useState(false);
    const [error, setError] = useState("");
    const [isFormLoading, setIsFormLoading] = useState(false);
    const [isGoogleLoading, setIsGoogleLoading] = useState(false);
    const [twoFactor, setTwoFactor] = useState(null);
    const { register, handleSubmit, formState: { errors }, } = useForm({ resolver: zodResolver(schema) });
    // ── Email / password submit ──────────────────────────────────────────────
    const onSubmit = async (data) => {
        setError("");
        setIsFormLoading(true);
        try {
            const result = await login(data.email, data.password);
            if (result.two_factor_required && result.email) {
                setTwoFactor({ required: true, email: result.email });
            }
            else {
                navigate("/dashboard");
            }
        }
        catch (err) {
            const d = err.response?.data;
            if (d?.detail) {
                setError(d.detail);
            }
            else if (d && typeof d === "object") {
                const key = Object.keys(d)[0];
                const msg = d[key];
                setError(`${key}: ${Array.isArray(msg) ? msg[0] : msg}`);
            }
            else if (err.message?.includes("Network")) {
                setError("Cannot reach the server. Check your connection.");
            }
            else {
                setError("Invalid email or password.");
            }
        }
        finally {
            setIsFormLoading(false);
        }
    };
    // ── Google OAuth ─────────────────────────────────────────────────────────
    const googleLogin = useGoogleLogin({
        onSuccess: async (tokenResponse) => {
            setIsGoogleLoading(true);
            setError("");
            try {
                const { data } = await authApi.googleLogin(tokenResponse.access_token);
                await handleLoginSuccess({ access: data.access, refresh: data.refresh });
                navigate("/dashboard");
            }
            catch (err) {
                setError(err.response?.data?.detail ||
                    "Google sign-in failed. Please try again.");
            }
            finally {
                setIsGoogleLoading(false);
            }
        },
        onError: () => {
            setIsGoogleLoading(false);
            setError("Google sign-in was cancelled or failed.");
        },
        flow: "implicit",
    });
    const busy = isFormLoading || isGoogleLoading;
    // ── 2FA resolved ─────────────────────────────────────────────────────────
    const handle2FASuccess = async (tokens) => {
        await handleLoginSuccess(tokens);
        setTwoFactor(null);
        navigate("/dashboard");
    };
    return (_jsxs(_Fragment, { children: [twoFactor?.required && (_jsx(TwoFactorModal, { email: twoFactor.email, onVerified: handle2FASuccess, onCancel: () => setTwoFactor(null) })), _jsxs("div", { className: "min-h-screen bg-[#080a0e] flex", children: [_jsxs("div", { className: "hidden lg:flex flex-col justify-between w-[45%] p-12 relative overflow-hidden", children: [_jsxs("div", { className: "absolute inset-0 overflow-hidden pointer-events-none", children: [_jsx("div", { className: "absolute -top-40 -left-40 w-[500px] h-[500px] rounded-full bg-indigo-600/20 blur-[120px]" }), _jsx("div", { className: "absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full bg-violet-600/15 blur-[100px]" })] }), _jsx("div", { className: "relative z-10", children: _jsxs("div", { className: "flex items-center gap-3", children: [_jsx("div", { className: "w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center", children: _jsx("svg", { className: "w-5 h-5 text-white", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor", strokeWidth: 2, children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", d: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" }) }) }), _jsx("span", { className: "text-white font-semibold text-lg tracking-tight", children: "DocFlow AI" })] }) }), _jsxs("div", { className: "relative z-10", children: [_jsxs("p", { className: "text-4xl font-bold text-white leading-tight mb-4", children: ["Contracts, invoices &", _jsx("br", {}), _jsx("span", { className: "text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400", children: "AI-powered reviews" }), _jsx("br", {}), "in one place."] }), _jsx("p", { className: "text-white/40 text-sm leading-relaxed max-w-xs", children: "Streamline your business documents with intelligent automation and real-time collaboration." })] }), _jsxs("div", { className: "relative z-10 flex items-center gap-3", children: [_jsx("div", { className: "flex -space-x-2", children: ["#6366f1", "#8b5cf6", "#a78bfa"].map((color, i) => (_jsx("div", { className: "w-8 h-8 rounded-full border-2 border-[#080a0e]", style: { background: color } }, i))) }), _jsx("p", { className: "text-white/30 text-xs", children: "Trusted by 2,000+ freelancers & agencies" })] })] }), _jsx("div", { className: "flex-1 flex items-center justify-center p-6 lg:p-12", children: _jsxs("div", { className: "w-full max-w-[420px]", children: [_jsxs("div", { className: "flex items-center gap-2 mb-8 lg:hidden", children: [_jsx("div", { className: "w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center", children: _jsx("svg", { className: "w-4 h-4 text-white", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor", strokeWidth: 2, children: _jsx("path", { strokeLinecap: "round", strokeLinejoin: "round", d: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" }) }) }), _jsx("span", { className: "text-white font-semibold", children: "DocFlow AI" })] }), _jsx("h1", { className: "text-2xl font-bold text-white mb-1", children: "Welcome back" }), _jsx("p", { className: "text-white/40 text-sm mb-8", children: "Sign in to continue to your workspace" }), error && (_jsxs("div", { className: "flex items-start gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 mb-6", children: [_jsxs("svg", { className: "w-4 h-4 text-red-400 mt-0.5 shrink-0", fill: "none", viewBox: "0 0 24 24", stroke: "currentColor", strokeWidth: 2, children: [_jsx("circle", { cx: "12", cy: "12", r: "10" }), _jsx("path", { strokeLinecap: "round", d: "M12 8v4m0 4h.01" })] }), _jsx("p", { className: "text-red-400 text-sm", children: error })] })), _jsx("button", { onClick: () => googleLogin(), disabled: busy, className: "group relative w-full flex items-center justify-center gap-3 bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 rounded-xl px-4 py-3 text-sm font-medium text-white/80 hover:text-white transition-all duration-200 disabled:opacity-40 mb-5", children: isGoogleLoading ? (_jsx(Loader2, { className: "w-4 h-4 animate-spin text-white/60" })) : (_jsxs(_Fragment, { children: [_jsxs("svg", { className: "w-5 h-5", viewBox: "0 0 24 24", children: [_jsx("path", { d: "M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z", fill: "#4285F4" }), _jsx("path", { d: "M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z", fill: "#34A853" }), _jsx("path", { d: "M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z", fill: "#FBBC05" }), _jsx("path", { d: "M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z", fill: "#EA4335" })] }), "Continue with Google"] })) }), _jsxs("div", { className: "flex items-center gap-4 mb-5", children: [_jsx("div", { className: "flex-1 h-px bg-white/8" }), _jsx("span", { className: "text-white/25 text-xs", children: "or" }), _jsx("div", { className: "flex-1 h-px bg-white/8" })] }), _jsxs("form", { onSubmit: handleSubmit(onSubmit), className: "space-y-4", children: [_jsxs("div", { children: [_jsx("label", { className: "block text-xs font-medium text-white/50 mb-1.5 uppercase tracking-wider", children: "Email" }), _jsx("input", { ...register("email"), type: "email", disabled: busy, placeholder: "you@company.com", className: `w-full bg-white/5 border rounded-xl px-4 py-3 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 transition-all duration-200 disabled:opacity-40 ${errors.email
                                                        ? "border-red-500/50 focus:ring-red-500/30"
                                                        : "border-white/10 hover:border-white/20 focus:ring-indigo-500/40 focus:border-indigo-500/50"}` }), errors.email && (_jsx("p", { className: "text-red-400 text-xs mt-1.5", children: errors.email.message }))] }), _jsxs("div", { children: [_jsxs("div", { className: "flex justify-between items-center mb-1.5", children: [_jsx("label", { className: "block text-xs font-medium text-white/50 uppercase tracking-wider", children: "Password" }), _jsx(Link, { to: "/forgot-password", className: "text-xs text-indigo-400 hover:text-indigo-300 transition-colors", children: "Forgot password?" })] }), _jsxs("div", { className: "relative", children: [_jsx("input", { ...register("password"), type: showPass ? "text" : "password", disabled: busy, placeholder: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", className: `w-full bg-white/5 border rounded-xl px-4 py-3 text-sm text-white placeholder:text-white/20 focus:outline-none focus:ring-2 pr-12 transition-all duration-200 disabled:opacity-40 ${errors.password
                                                                ? "border-red-500/50 focus:ring-red-500/30"
                                                                : "border-white/10 hover:border-white/20 focus:ring-indigo-500/40 focus:border-indigo-500/50"}` }), _jsx("button", { type: "button", onClick: () => setShowPass(!showPass), className: "absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60 transition-colors p-1", children: showPass ? (_jsx(EyeOff, { className: "w-4 h-4" })) : (_jsx(Eye, { className: "w-4 h-4" })) })] }), errors.password && (_jsx("p", { className: "text-red-400 text-xs mt-1.5", children: errors.password.message }))] }), _jsx("button", { type: "submit", disabled: busy, className: "group w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white font-medium py-3 rounded-xl transition-all duration-200 flex items-center justify-center gap-2 mt-2", children: isFormLoading ? (_jsx(Loader2, { className: "w-4 h-4 animate-spin" })) : (_jsxs(_Fragment, { children: ["Sign In", _jsx(ArrowRight, { className: "w-4 h-4 group-hover:translate-x-0.5 transition-transform" })] })) })] }), _jsxs("p", { className: "text-center text-sm text-white/30 mt-6", children: ["No account?", " ", _jsx(Link, { to: "/register", className: "text-indigo-400 hover:text-indigo-300 font-medium transition-colors", children: "Create one free" })] })] }) })] })] }));
}
