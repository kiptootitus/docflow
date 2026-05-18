import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { companiesApi } from "@/lib/api";
import type { Client } from "@/lib/api";

export default function ClientsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [form, setForm] = useState({ name: "", email: "", phone: "", address: "" });

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data } = useQuery({
    queryKey: ["clients"],
    queryFn: () => companiesApi.clients.list(company?.id),
    enabled: Boolean(company),
  });
  const clients = data?.data?.results ?? [];

  const createMutation = useMutation({
    mutationFn: () => companiesApi.clients.create({ ...form, company: company!.id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["clients"] }); setShowForm(false); setForm({ name: "", email: "", phone: "", address: "" }); },
  });

  const updateMutation = useMutation({
    mutationFn: () => companiesApi.clients.update(editing!.id, form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["clients"] }); setEditing(null); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => companiesApi.clients.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });

  const openEdit = (c: Client) => { setEditing(c); setForm({ name: c.name, email: c.email, phone: c.phone, address: c.address }); };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Clients</h1>
          <p className="text-gray-500 text-sm mt-0.5">{clients.length} clients</p>
        </div>
        <button onClick={() => setShowForm(true)} className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors">
          <Plus className="w-4 h-4" /> Add Client
        </button>
      </div>

      {/* Form Modal */}
      {(showForm || editing) && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">{editing ? "Edit Client" : "Add Client"}</h2>
            <div className="space-y-3">
              {(["name","email","phone","address"] as const).map(k => (
                <div key={k}>
                  <label className="block text-xs font-medium text-gray-600 uppercase tracking-wide mb-1 capitalize">{k}</label>
                  <input value={form[k]} onChange={e => setForm(p => ({ ...p, [k]: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
              ))}
            </div>
            <div className="flex gap-2 mt-4">
              <button onClick={() => { setShowForm(false); setEditing(null); }} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50">Cancel</button>
              <button onClick={() => editing ? updateMutation.mutate() : createMutation.mutate()} className="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-indigo-700">
                {editing ? "Save Changes" : "Add Client"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {clients.map((c) => (
          <div key={c.id} className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm group">
            <div className="flex items-start justify-between">
              <div>
                <div className="w-10 h-10 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-700 font-semibold mb-3">
                  {c.name[0]}
                </div>
                <h3 className="font-semibold text-gray-900">{c.name}</h3>
                <p className="text-sm text-gray-500">{c.email}</p>
                {c.phone && <p className="text-sm text-gray-400">{c.phone}</p>}
              </div>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={() => openEdit(c)} className="p-1.5 text-gray-400 hover:text-indigo-600"><Pencil className="w-3.5 h-3.5" /></button>
                <button onClick={() => { if (confirm("Delete client?")) deleteMutation.mutate(c.id); }} className="p-1.5 text-gray-400 hover:text-red-500"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
