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
    mutationFn: (plan: string) => billingApi.createCheckout(plan),
    onSuccess: (res) => { window.location.href = res.data.checkout_url; },
  });
  const portalMutation = useMutation({
    mutationFn: () => billingApi.openPortal(),
    onSuccess: (res) => { window.location.href = res.data.portal_url; },
  });

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Billing & Plans</h1>
        <p className="text-gray-500 mt-1">Choose the right plan for your business.</p>
      </div>

      <div className="flex justify-end mb-6">
        <button onClick={() => portalMutation.mutate()} className="flex items-center gap-2 text-sm text-indigo-600 hover:underline font-medium">
          <CreditCard className="w-4 h-4" /> Manage Subscription
        </button>
      </div>

      <div className="grid grid-cols-3 gap-6 max-w-4xl">
        {PLANS.map((plan) => (
          <div key={plan.id} className={`bg-white rounded-2xl border p-6 relative ${plan.popular ? "border-indigo-500 shadow-md" : "border-gray-100 shadow-sm"}`}>
            {plan.popular && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-indigo-600 text-white text-xs font-semibold px-3 py-1 rounded-full">
                Most Popular
              </div>
            )}
            <div className="mb-4">
              <div className="w-10 h-10 bg-indigo-50 rounded-xl flex items-center justify-center mb-3">
                <Zap className="w-5 h-5 text-indigo-600" />
              </div>
              <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
              <div className="flex items-baseline gap-1 mt-1">
                <span className="text-3xl font-bold text-gray-900">${plan.price}</span>
                <span className="text-gray-400">/month</span>
              </div>
            </div>
            <ul className="space-y-2 mb-6">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                  <Check className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                  {f}
                </li>
              ))}
            </ul>
            <button
              onClick={() => checkoutMutation.mutate(plan.id)}
              disabled={checkoutMutation.isPending}
              className={`w-full py-2.5 rounded-xl font-medium text-sm transition-colors ${plan.popular ? "bg-indigo-600 text-white hover:bg-indigo-700" : "bg-gray-100 text-gray-700 hover:bg-gray-200"}`}
            >
              {checkoutMutation.isPending ? "Loading…" : "Get Started"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
