import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useMutation } from "@tanstack/react-query";
import { CreditCard, Check, Zap } from "lucide-react";
import { billingApi } from "@/lib/api";
const PLANS = [
    { id: "starter", name: "Starter", price: 19, features: ["Up to 50 invoices/mo", "PDF generation", "Client portal", "Email sending"] },
    { id: "pro", name: "Pro", price: 49, popular: true, features: ["Unlimited invoices", "AI contract review", "AI document generation", "Multi-currency", "Integrations"] },
    { id: "enterprise", name: "Enterprise", price: 199, features: ["Everything in Pro", "Custom branding", "Priority support", "Dedicated onboarding", "SLA guarantee"] },
];
export default function BillingPage() {
    const checkoutMutation = useMutation({
        mutationFn: (plan) => billingApi.createCheckout(plan),
        onSuccess: (res) => { window.location.href = res.data.checkout_url; },
    });
    const portalMutation = useMutation({
        mutationFn: () => billingApi.openPortal(),
        onSuccess: (res) => { window.location.href = res.data.portal_url; },
    });
    return (_jsxs("div", { className: "p-4 sm:p-8", children: [_jsxs("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8", children: [_jsxs("div", { children: [_jsx("h1", { className: "text-xl sm:text-2xl font-bold text-gray-900", children: "Billing & Plans" }), _jsx("p", { className: "text-gray-500 text-sm mt-1", children: "Choose the right plan for your business." })] }), _jsx("div", { className: "flex justify-start sm:justify-end", children: _jsxs("button", { onClick: () => portalMutation.mutate(), disabled: portalMutation.isPending, className: "flex items-center gap-2 text-sm text-indigo-600 hover:underline font-medium p-1 disabled:opacity-50", children: [_jsx(CreditCard, { className: "w-4 h-4" }), portalMutation.isPending ? "Opening Portal..." : "Manage Subscription"] }) })] }), _jsx("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-5xl mx-auto", children: PLANS.map((plan) => (_jsxs("div", { className: `bg-white rounded-2xl border p-6 flex flex-col justify-between relative transition-all ${plan.popular
                        ? "border-indigo-500 shadow-md ring-1 ring-indigo-500/10 mt-3 md:mt-0"
                        : "border-gray-200/80 shadow-sm"}`, children: [plan.popular && (_jsx("div", { className: "absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-[11px] font-bold px-3 py-1 rounded-full uppercase tracking-wider whitespace-nowrap shadow-sm", children: "Most Popular" })), _jsxs("div", { children: [_jsxs("div", { className: "mb-5", children: [_jsx("div", { className: "w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center mb-4 select-none", children: _jsx(Zap, { className: "w-5 h-5 text-indigo-600" }) }), _jsx("h3", { className: "text-lg font-bold text-gray-900", children: plan.name }), _jsxs("div", { className: "flex items-baseline gap-1 mt-1", children: [_jsxs("span", { className: "text-3xl font-bold text-gray-900", children: ["$", plan.price] }), _jsx("span", { className: "text-gray-400 text-sm", children: "/month" })] })] }), _jsx("ul", { className: "space-y-3 mb-8", children: plan.features.map((f) => (_jsxs("li", { className: "flex items-start gap-2.5 text-sm text-gray-600", children: [_jsx(Check, { className: "w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" }), _jsx("span", { children: f })] }, f))) })] }), _jsx("button", { onClick: () => checkoutMutation.mutate(plan.id), disabled: checkoutMutation.isPending, className: `w-full py-2.5 rounded-xl font-semibold text-sm transition-colors shadow-xs ${plan.popular
                                ? "bg-indigo-600 text-white hover:bg-indigo-700"
                                : "bg-gray-100 text-gray-700 hover:bg-gray-200"} disabled:opacity-50`, children: checkoutMutation.isPending ? "Redirecting..." : "Get Started" })] }, plan.id))) })] }));
}
