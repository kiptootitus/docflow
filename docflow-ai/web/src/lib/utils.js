import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs) {
    return twMerge(clsx(inputs));
}
export function formatCurrency(amount, currency = "KES") {
    const num = typeof amount === "string" ? parseFloat(amount) : amount;
    return new Intl.NumberFormat("en-KE", {
        style: "currency",
        currency,
        minimumFractionDigits: 2,
    }).format(num);
}
export function formatDate(date) {
    return new Date(date).toLocaleDateString("en-KE", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}
export const STATUS_COLORS = {
    draft: "bg-gray-100 text-gray-700",
    sent: "bg-blue-100 text-blue-700",
    viewed: "bg-purple-100 text-purple-700",
    paid: "bg-green-100 text-green-700",
    overdue: "bg-red-100 text-red-700",
    cancelled: "bg-gray-100 text-gray-500",
    pending: "bg-yellow-100 text-yellow-700",
    signed: "bg-green-100 text-green-700",
    completed: "bg-emerald-100 text-emerald-700",
    expired: "bg-red-100 text-red-700",
};
