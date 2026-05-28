import { useQuery } from "@tanstack/react-query";
import { TrendingUp, FileText, Clock, FileSignature, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { invoicesApi, companiesApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";
import { formatCurrency, formatDate, STATUS_COLORS, cn } from "@/lib/utils";

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-4 sm:p-6 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs sm:text-sm text-gray-500 font-medium truncate">{label}</p>
          <p className="text-xl sm:text-2xl font-bold text-gray-900 mt-1 truncate">{value}</p>
        </div>
        <div
          className={cn(
            "w-10 h-10 sm:w-12 sm:h-12 rounded-xl flex items-center justify-center flex-shrink-0",
            color
          )}
        >
          <Icon className="w-5 h-5 sm:w-6 sm:h-6" />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuthStore();

  // ── Company ──────────────────────────────────────────────────────────────
  const { data: companiesData } = useQuery({
    queryKey: ["companies"],
    queryFn: () => companiesApi.list(),
  });

  // The backend returns { count, results: Company[] }
  const company = companiesData?.data?.results?.[0];

  // "currency" is the correct field name on the Company model.
  // Falls back to "USD" if no company exists yet.
  const currency = company?.currency ?? "USD";

  // ── Invoices ─────────────────────────────────────────────────────────────
  const { data: invoicesData } = useQuery({
    queryKey: ["invoices", "recent"],
    queryFn: () => invoicesApi.list({ ordering: "-created_at" }),
  });

  const invoices = invoicesData?.data?.results ?? [];
  const paid    = invoices.filter((i) => i.status === "paid");
  const pending = invoices.filter(
    (i) => i.status === "sent" || i.status === "viewed"
  );

  const totalRevenue = paid.reduce(
    (sum, i) => sum + parseFloat(i.total_amount || "0"),
    0
  );
  const totalPending = pending.reduce(
    (sum, i) => sum + parseFloat(i.total_amount || "0"),
    0
  );

  return (
    <div className="p-4 sm:p-8">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">
            Welcome back, {user?.first_name ?? "there"} 👋
          </h1>
          <p className="text-sm text-gray-500 mt-1">Here's your business overview</p>
        </div>
        <Link
          to="/invoices/new"
          className="flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors text-sm w-full sm:w-auto shadow-sm"
        >
          <Plus className="w-4 h-4" />
          New Invoice
        </Link>
      </div>

      {/* ── Stats ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-8">
        <StatCard
          label="Total Revenue"
          value={formatCurrency(totalRevenue, currency)}
          icon={TrendingUp}
          color="bg-green-50 text-green-600"
        />
        <StatCard
          label="Invoices Sent"
          value={invoicesData?.data?.count ?? 0}
          icon={FileText}
          color="bg-blue-50 text-blue-600"
        />
        <StatCard
          label="Pending"
          value={formatCurrency(totalPending, currency)}
          icon={Clock}
          color="bg-amber-50 text-amber-600"
        />
        <StatCard
          label="Paid Invoices"
          value={paid.length}
          icon={FileSignature}
          color="bg-indigo-50 text-indigo-600"
        />
      </div>

      {/* ── Recent Invoices ─────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900 text-sm sm:text-base">Recent Invoices</h2>
          <Link
            to="/invoices"
            className="text-sm text-indigo-600 hover:underline font-medium"
          >
            View all
          </Link>
        </div>

        <div className="divide-y divide-gray-50 overflow-x-auto">
          {invoices.slice(0, 8).map((invoice) => (
            <Link
              key={invoice.id}
              to={`/invoices/${invoice.id}`}
              className="flex items-center justify-between px-4 sm:px-6 py-4 hover:bg-gray-50 transition-colors min-w-[500px] sm:min-w-0"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {invoice.number}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {invoice.client_name ?? "No client"}
                </p>
              </div>

              <div className="text-right mx-4">
                <p className="text-sm font-semibold text-gray-900">
                  {formatCurrency(parseFloat(invoice.total_amount || "0"), invoice.currency)}
                </p>
              </div>

              <div className="flex items-center gap-4">
                <span
                  className={cn(
                    "text-[11px] sm:text-xs font-medium px-2.5 py-1 rounded-full capitalize text-center min-w-[70px]",
                    STATUS_COLORS[invoice.status]
                  )}
                >
                  {invoice.status}
                </span>
                <p className="text-xs text-gray-400 w-20 text-right">
                  {formatDate(invoice.created_at)}
                </p>
              </div>
            </Link>
          ))}

          {invoices.length === 0 && (
            <div className="px-6 py-12 text-center">
              <FileText className="w-10 h-10 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 text-sm">No invoices yet.</p>
              <Link
                to="/invoices/new"
                className="text-sm text-indigo-600 hover:underline mt-1 inline-block"
              >
                Create your first invoice
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}