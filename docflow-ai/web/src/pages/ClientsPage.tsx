import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, Loader2, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { invoicesApi, companiesApi } from "@/lib/api";
import type { Invoice } from "@/lib/api";

// ---------------------------------------------------------------------------
// Derive a unique client list from invoices.
// There is no standalone /clients/ endpoint — clients are stored as inline
// fields (client_name, client_email, etc.) on each document.
// ---------------------------------------------------------------------------

interface DerivedClient {
  key: string;           // dedup key
  name: string;
  email: string;
  phone: string;
  address: string;
  invoiceCount: number;
  totalBilled: number;
  currency: string;
  lastInvoiceId: string;
}

function deriveClients(invoices: Invoice[]): DerivedClient[] {
  const map = new Map<string, DerivedClient>();

  for (const inv of invoices) {
    const email = inv.client_email?.trim().toLowerCase() ?? "";
    const name  = inv.client_name?.trim() ?? "";
    const key   = email || name || inv.id; // fallback to invoice id if both blank

    if (!map.has(key)) {
      map.set(key, {
        key,
        name,
        email,
        phone:        "",
        address:      "",
        invoiceCount: 0,
        totalBilled:  0,
        currency:     inv.currency ?? "USD",
        lastInvoiceId: inv.id,
      });
    }

    const c = map.get(key)!;
    c.invoiceCount += 1;
    c.totalBilled  += parseFloat(inv.total_amount || (inv as any).total || "0");
    c.lastInvoiceId = inv.id; // keep the most recent
  }

  return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name));
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ClientsPage() {
  // Company — needed for the subtitle only
  const { data: companiesData, isLoading: isLoadingCompany } = useQuery({
    queryKey: ["companies"],
    queryFn:  () => companiesApi.list(),
  });
  const company = companiesData?.data?.results?.[0];

  // All invoices — fetch a large page so we capture most clients
  const { data: invoicesData, isLoading: isLoadingInvoices } = useQuery({
    queryKey: ["invoices", "all-for-clients"],
    queryFn:  () => invoicesApi.list({ page_size: "200", ordering: "-created_at" }),
    enabled:  Boolean(company?.id),
  });

  const invoices = invoicesData?.data?.results ?? [];
  const clients  = useMemo(() => deriveClients(invoices), [invoices]);

  // ── Loading ──────────────────────────────────────────────────────────────
  if (isLoadingCompany || (company?.id && isLoadingInvoices)) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
        <p className="text-gray-500 text-sm font-medium">Loading clients…</p>
      </div>
    );
  }

  // ── No company yet ───────────────────────────────────────────────────────
  if (!company) {
    return (
      <div className="p-4 sm:p-8 text-center text-gray-500 text-sm mt-16">
        Set up your company workspace first before viewing clients.
      </div>
    );
  }

  // ── Main view ────────────────────────────────────────────────────────────
  return (
    <div className="p-4 sm:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Clients</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            {clients.length} unique client{clients.length !== 1 ? "s" : ""} from invoices
            {company?.name ? ` · ${company.name}` : ""}
          </p>
        </div>
        <Link
          to="/invoices/new"
          className="flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors w-full sm:w-auto shadow-sm"
        >
          <FileText className="w-4 h-4" /> New Invoice
        </Link>
      </div>

      {/* Client cards */}
      {clients.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {clients.map((c) => (
            <Link
              key={c.key}
              to={`/invoices?client_email=${encodeURIComponent(c.email)}`}
              className="bg-white rounded-xl border border-gray-100 p-4 sm:p-5 shadow-sm hover:border-gray-200 hover:shadow-md transition-all"
            >
              <div className="flex items-start gap-3">
                {/* Avatar */}
                <div className="w-10 h-10 bg-indigo-50 text-indigo-700 rounded-full flex items-center justify-center font-bold text-sm flex-shrink-0 select-none">
                  {c.name ? c.name[0].toUpperCase() : "?"}
                </div>

                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-gray-900 text-sm sm:text-base truncate">
                    {c.name || "Unnamed client"}
                  </h3>
                  {c.email && (
                    <p className="text-xs sm:text-sm text-gray-500 truncate mt-0.5">{c.email}</p>
                  )}

                  {/* Stats row */}
                  <div className="flex items-center gap-3 mt-2.5">
                    <span className="text-[11px] bg-gray-50 border border-gray-100 text-gray-500 rounded-md px-2 py-0.5">
                      {c.invoiceCount} invoice{c.invoiceCount !== 1 ? "s" : ""}
                    </span>
                    <span className="text-[11px] font-semibold text-indigo-600">
                      {new Intl.NumberFormat("en", {
                        style:    "currency",
                        currency: c.currency,
                        maximumFractionDigits: 0,
                      }).format(c.totalBilled)}
                    </span>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="text-center bg-white border border-gray-100 rounded-xl p-12 max-w-md mx-auto shadow-sm mt-4">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm font-medium">No clients yet.</p>
          <p className="text-gray-400 text-xs mt-1">
            Clients appear here once you create invoices with client details.
          </p>
          <Link
            to="/invoices/new"
            className="text-indigo-600 text-sm font-semibold hover:underline mt-3 inline-block"
          >
            Create your first invoice
          </Link>
        </div>
      )}
    </div>
  );
}