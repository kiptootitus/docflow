import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Users, Building2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Client } from "@/lib/api";

export default function ClientsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Client | null>(null);
  const [form, setForm] = useState({ name: "", email: "", phone: "", address: "" });

  // Onboarding company form tracking states
  const [newCompanyName, setNewCompanyName] = useState("");
  const [newCompanyEmail, setNewCompanyEmail] = useState("");

  // 1. Fetch Companies - Force the trailing slash explicitly with "/" instead of ""
  const { data: companiesData, isLoading: isLoadingCompany } = useQuery({
    queryKey: ["companies"],
    queryFn: () => api.get("/")
  });

  const company = companiesData?.data?.results?.[0];

  // 2. Fetch Clients - Targets GET /api/v1/clients/
  const { data, isLoading: isLoadingClients } = useQuery({
    queryKey: ["clients", company?.id],
    queryFn: () => api.get("/clients/"),
    enabled: Boolean(company?.id),
  });
  const clients = data?.data?.results ?? [];

  // Mutation to create a company profile hitting the exact backend root path: POST /api/v1/
  const createCompanyMutation = useMutation({
    mutationFn: (payload: { name: string; email: string }) => api.post("/", payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["companies"] });
      setNewCompanyName("");
      setNewCompanyEmail("");
    },
    onError: (err: any) => {
      console.error(err);
      alert(`Error creating business workspace: ${err.response?.data?.detail || "Please check validation rules."}`);
    }
  });

  // Client Mutations pointing directly to the /clients/ endpoint route layout
  const createMutation = useMutation({
    mutationFn: (newClient: Omit<Client, "id">) => api.post("/clients/", newClient),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      setShowForm(false);
      setForm({ name: "", email: "", phone: "", address: "" });
    },
    onError: (err: any) => {
      alert(`Error creating client: ${err.response?.data?.detail || "Please check parameters"}`);
    }
  });

  const updateMutation = useMutation({
    mutationFn: (updatedData: Partial<Client>) => api.put(`/clients/${editing!.id}/`, updatedData),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      setEditing(null);
      setForm({ name: "", email: "", phone: "", address: "" });
    },
    onError: (err: any) => {
      alert(`Error updating client: ${err.response?.data?.detail || "Please check parameters"}`);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/clients/${id}/`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });

  const openEdit = (c: Client) => {
    setEditing(c);
    setForm({ name: c.name, email: c.email, phone: c.phone || "", address: c.address || "" });
    setShowForm(true);
  };

  const handleFormSubmit = () => {
    if (!form.name || !form.email) {
      alert("Name and Email are required fields.");
      return;
    }

    if (!company?.id) {
      alert("System could not verify your business identity. Please ensure workspace setup is complete.");
      return;
    }

    if (editing) {
      updateMutation.mutate(form);
    } else {
      createMutation.mutate({
        ...form,
        company: company.id
      });
    }
  };

  // Sync Loading state context wrapper
  if (isLoadingCompany || (company?.id && isLoadingClients)) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-3">
        <Loader2 className="w-8 h-8 text-indigo-600 animate-spin" />
        <p className="text-gray-500 text-sm font-medium">Syncing profile accounts...</p>
      </div>
    );
  }

  // Workspace Setup Fallback Form View
  if (!company) {
    return (
      <div className="max-w-md mx-auto mt-16 p-6 bg-white border border-gray-100 rounded-2xl shadow-sm text-center">
        <div className="w-12 h-12 bg-indigo-50 text-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-4">
          <Building2 className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-gray-900">Create your Business Profile</h2>
        <p className="text-gray-500 text-sm mt-1 mb-6">
          Before adding clients, you need to create a profile space for your company identity.
        </p>
        <div className="space-y-4 text-left">
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Company / Trading Name
            </label>
            <input
              type="text"
              placeholder="e.g. Acme Corp"
              value={newCompanyName}
              onChange={(e) => setNewCompanyName(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
              Business Email Address
            </label>
            <input
              type="email"
              placeholder="e.g. billing@acme.com"
              value={newCompanyEmail}
              onChange={(e) => setNewCompanyEmail(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
            />
          </div>

          <button
            onClick={() => {
              if (!newCompanyName.trim() || !newCompanyEmail.trim()) {
                return alert("Please fill out both Name and Email fields.");
              }
              createCompanyMutation.mutate({
                name: newCompanyName,
                email: newCompanyEmail,
              });
            }}
            disabled={createCompanyMutation.isPending}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 shadow-xs transition-colors disabled:opacity-50 mt-2"
          >
            {createCompanyMutation.isPending ? "Creating Space..." : "Set Up Workspace"}
          </button>
        </div>
      </div>
    );
  }

  // Primary Working Interface Layout Presenter
  return (
    <div className="p-4 sm:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Clients</h1>
          <p className="text-gray-500 text-sm mt-0.5">{clients.length} clients registered under {company.name}</p>
        </div>
        <button
          onClick={() => { setEditing(null); setForm({ name: "", email: "", phone: "", address: "" }); setShowForm(true); }}
          className="flex items-center justify-center gap-2 bg-indigo-600 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 transition-colors w-full sm:w-auto shadow-sm"
        >
          <Plus className="w-4 h-4" /> Add Client
        </button>
      </div>

      {/* Entry Modal Overlay Form Component */}
      {(showForm || editing) && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-5 sm:p-6 border border-gray-100 max-h-[90vh] overflow-y-auto">
            <h2 className="text-base sm:text-lg font-semibold text-gray-900 mb-4">
              {editing ? "Edit Client" : "Add Client"}
            </h2>
            <div className="space-y-3.5">
              {(["name", "email", "phone", "address"] as const).map(k => (
                <div key={k}>
                  <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1 capitalize">
                    {k}
                  </label>
                  <input
                    value={form[k]}
                    type={k === "email" ? "email" : "text"}
                    onChange={e => setForm(p => ({ ...p, [k]: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-5">
              <button
                type="button"
                onClick={() => { setShowForm(false); setEditing(null); }}
                className="flex-1 border border-gray-200 py-2 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 bg-white"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleFormSubmit}
                disabled={createMutation.isPending || updateMutation.isPending}
                className="flex-1 bg-indigo-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 shadow-xs disabled:opacity-50"
              >
                {createMutation.isPending || updateMutation.isPending ? "Saving..." : editing ? "Save Changes" : "Add Client"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cards Client Entries Presentation Layer */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {clients.map((c) => (
          <div key={c.id} className="bg-white rounded-xl border border-gray-100 p-4 sm:p-5 shadow-sm group hover:border-gray-200 transition-all">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="w-10 h-10 bg-indigo-50 text-indigo-700 rounded-full flex items-center justify-center font-bold text-sm tracking-wide mb-3 select-none">
                  {c.name ? c.name[0].toUpperCase() : "?"}
                </div>
                <h3 className="font-semibold text-gray-900 text-sm sm:text-base truncate">{c.name}</h3>
                <p className="text-xs sm:text-sm text-gray-500 truncate mt-0.5">{c.email}</p>
                {c.phone && <p className="text-xs sm:text-sm text-gray-400 mt-0.5 truncate">{c.phone}</p>}
              </div>

              <div className="flex gap-0.5 opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                <button
                  onClick={() => openEdit(c)}
                  className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-gray-50 rounded-md transition-colors"
                  title="Edit Client"
                >
                  <Pencil className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => { if (confirm("Delete client?")) deleteMutation.mutate(c.id); }}
                  className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50/50 rounded-md transition-colors"
                  title="Delete Client"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Empty Fallback Block view */}
      {clients.length === 0 && (
        <div className="text-center bg-white border border-gray-100 rounded-xl p-12 max-w-md mx-auto shadow-sm mt-4">
          <Users className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm font-medium">No clients recorded yet.</p>
          <button
            onClick={() => setShowForm(true)}
            className="text-indigo-600 text-sm font-semibold hover:underline mt-1 inline-block"
          >
            Add your first business client
          </button>
        </div>
      )}
    </div>
  );
}