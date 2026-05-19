import axios, { type AxiosInstance } from "axios";

const API_URL = import.meta.env.VITE_API_URL || "";

export const api: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api/v1`,
  withCredentials: true,
});

// Attach token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token"); // 👈 Pulls your active token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`; // 👈 Injects it seamlessly
  }
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_URL}/api/v1/auth/token/refresh/`, { refresh });
          localStorage.setItem("access_token", data.access);
          original.headers.Authorization = `Bearer ${data.access}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(err);
  }
);

// -- Types ------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: "owner" | "staff" | "accountant" | "client";
  avatar: string | null;
  created_at: string;
}

export interface Company {
  id: string;
  name: string;
  logo: string | null;
  email: string;
  phone: string;
  address_line1: string;
  city: string;
  country: string;
  vat_number: string;
  tax_rate: string;
  default_currency: string;
  branding_color: string;
  invoice_prefix: string;
  payment_due_days: number;
}

export interface Client {
  id: string;
  company: string;
  name: string;
  email: string;
  phone: string;
  address: string;
}

export interface LineItem {
  id?: string;
  description: string;
  quantity: number;
  unit_price: string;
  amount?: string;
  order: number;
}

export interface Invoice {
  id: string;
  company: string;
  client: string | null;
  client_name: string | null;
  number: string;
  status: "draft" | "sent" | "viewed" | "paid" | "overdue" | "cancelled";
  currency: string;
  issue_date: string;
  due_date: string | null;
  notes: string;
  terms: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  discount_amount: string;
  total_amount: string;
  line_items: LineItem[];
  portal_url: string;
  stripe_payment_link: string;
  sent_at: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface Contract {
  id: string;
  company: string;
  client: string | null;
  title: string;
  contract_type: string;
  content: string;
  status: "draft" | "pending" | "signed" | "completed" | "expired";
  start_date: string | null;
  end_date: string | null;
  value: string | null;
  currency: string;
  created_at: string;
}

export interface AiReview {
  id: string;
  document_name: string;
  review_results: Array<{
    type: "risk" | "suggestion" | "compliant" | "note";
    severity: "high" | "medium" | "low";
    title: string;
    description: string;
    clause_reference: string;
    recommendation: string;
  }>;
  status: "pending" | "processing" | "completed" | "failed";
  model_used: string;
  tokens_used: number;
  created_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Quotation {
  id: string;
  company: string;
  client: string;
  client_name: string;
  number: string;
  title?: string;
  status: "draft" | "sent" | "viewed" | "accepted" | "declined" | "expired";
  currency: string;
  issue_date: string;
  expiry_date: string | null;
  notes: string;
  terms: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  discount_amount: string;
  total_amount: string;
  portal_url: string;
  line_items: Array<{
    description: string;
    quantity: number;
    unit_price: string;
    amount: string;
  }>;
}

// -- API Calls --------------------------------------------------------------

export const authApi = {
  register: (data: { email: string; first_name: string; last_name: string; password: string; password_confirm: string }) =>
    api.post<{ user: User; tokens: { access: string; refresh: string } }>("/auth/register/", data),
  login: (email: string, password: string) =>
    api.post<{ access: string; refresh: string }>("/auth/login/", { email, password }),
  logout: (refresh: string) => api.post("/auth/logout/", { refresh }),
  me: () => api.get<User>("/auth/me/"),
  updateMe: (data: Partial<User>) => api.patch<User>("/auth/me/", data),
};

export const companiesApi = {
  list: () => api.get<PaginatedResponse<Company>>("/companies/"),
  get: (id: string) => api.get<Company>(`/companies/${id}/`),
  create: (data: Partial<Company>) => api.post<Company>("/companies/", data),
  update: (id: string, data: Partial<Company>) => api.patch<Company>(`/companies/${id}/`, data),
  stats: (id: string) => api.get(`/companies/${id}/stats/`),
  clients: {
    // Exact structural mapping to matching Swagger entries with explicit trailing slashes
    list: (companyId?: string) =>
      api.get<PaginatedResponse<Client>>(`/companies/clients/${companyId ? `?company=${companyId}` : ""}`),
    create: (data: Partial<Client>) =>
      api.post<Client>("/companies/clients/", data), // 👈 Restored & fixed with trailing slash
    update: (id: string, data: Partial<Client>) =>
      api.patch<Client>(`/companies/clients/${id}/`, data),
    delete: (id: string) =>
      api.delete(`/companies/clients/${id}/`),
  },
};

export const quotationsApi = {
  list: (params?: Record<string, any>) =>
    api.get<{ count: number; results: Quotation[] }>("/documents/quotations/", { params }),
  get: (id: string) =>
    api.get<Quotation>(`/documents/quotations/${id}/`),
  create: (data: Partial<Quotation>) =>
    api.post<Quotation>("/documents/quotations/", data),
  update: (id: string, data: Partial<Quotation>) =>
    api.put<Quotation>(`/documents/quotations/${id}/`, data),
  delete: (id: string) =>
    api.delete(`/documents/quotations/${id}/`),
  send: (id: string) =>
    api.post(`/documents/quotations/${id}/send/`),
  duplicate: (id: string) =>
    api.post<Quotation>(`/documents/quotations/${id}/duplicate/`),
  convertToInvoice: (id: string) =>
    api.post<{ id: string }>(`/documents/quotations/${id}/convert-to-invoice/`),
};

export const invoicesApi = {
  list: (params?: Record<string, string>) => api.get<PaginatedResponse<Invoice>>("/documents/invoices/", { params }),
  get: (id: string) => api.get<Invoice>(`/documents/invoices/${id}/`),
  create: (data: Partial<Invoice>) => api.post<Invoice>("/documents/invoices/", data),
  update: (id: string, data: Partial<Invoice>) => api.patch<Invoice>(`/documents/invoices/${id}/`, data),
  delete: (id: string) => api.delete(`/documents/invoices/${id}/`),
  sendEmail: (id: string) => api.post(`/documents/invoices/${id}/send_email/`),
  markPaid: (id: string) => api.post(`/documents/invoices/${id}/mark_paid/`),
  generatePdf: (id: string) => api.post(`/documents/invoices/${id}/generate_pdf/`),
  duplicate: (id: string) => api.post<Invoice>(`/documents/invoices/${id}/duplicate/`),
  createPaymentLink: (id: string) => api.post<{ payment_link: string }>(`/billing/invoices/${id}/payment-link/`),
};

export const contractsApi = {
  list: (params?: Record<string, string>) => api.get<PaginatedResponse<Contract>>("/documents/contracts/", { params }),
  get: (id: string) => api.get<Contract>(`/documents/contracts/${id}/`),
  create: (data: Partial<Contract>) => api.post<Contract>("/documents/contracts/", data),
  update: (id: string, data: Partial<Contract>) => api.patch<Contract>(`/documents/contracts/${id}/`, data),
  delete: (id: string) => api.delete(`/documents/contracts/${id}/`),
};

export const aiApi = {
  reviewContract: (formData: FormData) => api.post<AiReview>("/ai/review/", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  }),
  listReviews: (companyId?: string) => api.get<AiReview[]>(`/ai/review/${companyId ? `?company=${companyId}` : ""}`),
  generateDocument: (data: { doc_type: string; fields: Record<string, string>; company: string }) =>
    api.post<{ id: string; content: string; model: string; tokens_used: number }>("/ai/generate/", data),
};

export const billingApi = {
  createCheckout: (plan: string) => api.post<{ checkout_url: string }>("/billing/checkout/", { plan }),
  openPortal: () => api.post<{ portal_url: string }>("/billing/portal/"),
};