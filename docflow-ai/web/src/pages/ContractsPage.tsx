// ContractsPage.tsx
import { useQuery } from "@tanstack/react-query";
import { FileSignature, Plus } from "lucide-react";
import { contractsApi } from "@/lib/api";
import { formatDate, STATUS_COLORS, cn } from "@/lib/utils";

export function ContractsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["contracts"], queryFn: () => contractsApi.list() });
  const contracts = data?.data?.results ?? [];

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contracts</h1>
          <p className="text-gray-500 text-sm mt-0.5">{contracts.length} total</p>
        </div>
        <button className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> New Contract
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Title</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Type</th>
              <th className="text-center px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">End Date</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {isLoading && <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400">Loading…</td></tr>}
            {!isLoading && contracts.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center">
                  <FileSignature className="w-10 h-10 text-gray-200 mx-auto mb-2" />
                  <p className="text-gray-400 text-sm">No contracts yet.</p>
                </td>
              </tr>
            )}
            {contracts.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">{c.title}</td>
                <td className="px-6 py-4 text-sm text-gray-500 capitalize">{c.contract_type}</td>
                <td className="px-6 py-4 text-center">
                  <span className={cn("text-xs font-medium px-2.5 py-1 rounded-full capitalize", STATUS_COLORS[c.status as keyof typeof STATUS_COLORS])}>
                    {c.status}
                  </span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{c.end_date ? formatDate(c.end_date) : "—"}</td>
                <td className="px-6 py-4 text-sm text-gray-500">{formatDate(c.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default ContractsPage;
