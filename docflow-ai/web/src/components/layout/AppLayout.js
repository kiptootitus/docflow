import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Users, FileSignature, Sparkles, Settings, CreditCard, LogOut, Menu, X, Calculator // Imported for the new Quotations item
 } from "lucide-react";
import { useAuthStore } from "@/lib/auth-store";
import { cn } from "@/lib/utils";
const NAV_ITEMS = [
    { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
    { to: "/invoices", icon: FileText, label: "Invoices" },
    { to: "/quotations", icon: Calculator, label: "Quotations" }, // Added item here
    { to: "/contracts", icon: FileSignature, label: "Contracts" },
    { to: "/clients", icon: Users, label: "Clients" },
    { to: "/ai-review", icon: Sparkles, label: "AI Review" },
];
const BOTTOM_ITEMS = [
    { to: "/billing", icon: CreditCard, label: "Billing" },
    { to: "/settings", icon: Settings, label: "Settings" },
];
export default function AppLayout() {
    const { user, logout } = useAuthStore();
    const navigate = useNavigate();
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const handleLogout = async () => {
        await logout();
        navigate("/login");
    };
    // Shared inner sidebar contents to avoid code repetition across desktop and mobile screens
    const SidebarContent = () => (_jsxs("div", { className: "flex flex-col h-full bg-white", children: [_jsx("div", { className: "px-6 py-5 border-b border-gray-100", children: _jsxs("div", { className: "flex items-center gap-2", children: [_jsx("div", { className: "w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center", children: _jsx(FileText, { className: "w-4 h-4 text-white" }) }), _jsx("span", { className: "font-bold text-gray-900 text-lg", children: "DocFlow AI" })] }) }), _jsx("nav", { className: "flex-1 px-3 py-4 space-y-1", children: NAV_ITEMS.map(({ to, icon: Icon, label }) => (_jsxs(NavLink, { to: to, onClick: () => setIsMobileMenuOpen(false), className: ({ isActive }) => cn("flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all", isActive
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"), children: [_jsx(Icon, { className: "w-4 h-4 flex-shrink-0" }), label] }, to))) }), _jsxs("div", { className: "px-3 py-4 border-t border-gray-100 space-y-1", children: [BOTTOM_ITEMS.map(({ to, icon: Icon, label }) => (_jsxs(NavLink, { to: to, onClick: () => setIsMobileMenuOpen(false), className: ({ isActive }) => cn("flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all", isActive
                            ? "bg-indigo-50 text-indigo-700"
                            : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"), children: [_jsx(Icon, { className: "w-4 h-4 flex-shrink-0" }), label] }, to))), _jsxs("div", { className: "flex items-center gap-3 px-3 py-2.5 mt-2", children: [_jsxs("div", { className: "w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold text-sm flex-shrink-0", children: [user?.first_name?.[0], user?.last_name?.[0]] }), _jsxs("div", { className: "flex-1 min-w-0", children: [_jsx("p", { className: "text-sm font-medium text-gray-900 truncate", children: user?.full_name }), _jsx("p", { className: "text-xs text-gray-500 capitalize", children: user?.role })] }), _jsx("button", { onClick: handleLogout, className: "p-1 text-gray-400 hover:text-red-500 transition-colors", title: "Logout", children: _jsx(LogOut, { className: "w-4 h-4" }) })] })] })] }));
    return (_jsxs("div", { className: "flex flex-col md:flex-row h-screen w-full overflow-hidden bg-gray-50", children: [_jsx("aside", { className: "hidden md:flex w-64 bg-white border-r border-gray-100 flex-col shadow-sm flex-shrink-0", children: _jsx(SidebarContent, {}) }), _jsxs("header", { className: "flex md:hidden items-center justify-between bg-white h-16 px-4 border-b border-gray-100 shadow-sm flex-shrink-0 w-full", children: [_jsxs("div", { className: "flex items-center gap-2", children: [_jsx("div", { className: "w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center", children: _jsx(FileText, { className: "w-3.5 h-3.5 text-white" }) }), _jsx("span", { className: "font-bold text-gray-900 text-base", children: "DocFlow AI" })] }), _jsx("button", { onClick: () => setIsMobileMenuOpen(true), className: "p-1.5 rounded-lg border border-gray-100 text-gray-600 hover:bg-gray-50 focus:outline-none", children: _jsx(Menu, { className: "w-5 h-5" }) })] }), isMobileMenuOpen && (_jsxs("div", { className: "fixed inset-0 z-50 flex md:hidden", children: [_jsx("div", { className: "fixed inset-0 bg-gray-900/30 backdrop-blur-xs transition-opacity duration-200", onClick: () => setIsMobileMenuOpen(false) }), _jsxs("div", { className: "relative w-64 max-w-xs h-full bg-white shadow-xl flex flex-col z-50", children: [_jsx("div", { className: "absolute top-4 right-4 z-50", children: _jsx("button", { onClick: () => setIsMobileMenuOpen(false), className: "p-1.5 rounded-lg bg-gray-50 text-gray-400 hover:text-gray-700", children: _jsx(X, { className: "w-4 h-4" }) }) }), _jsx(SidebarContent, {})] })] })), _jsx("main", { className: "flex-1 overflow-auto min-w-0", children: _jsx("div", { className: "p-4 md:p-8 max-w-7xl mx-auto w-full", children: _jsx(Outlet, {}) }) })] }));
}
