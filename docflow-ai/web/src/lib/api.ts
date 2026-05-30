import axios from "axios";
import type { AxiosInstance } from "axios";

// ---------------------------------------------------------------------------
// Base client
// ---------------------------------------------------------------------------

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

export const api: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api/v1`,
  withCredentials: true,
});

// ── Request interceptor ────────────────────────────────────────────────────
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor ───────────────────────────────────────────────────
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;

    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem("refresh_token");

      if (refresh) {
        try {
          const { data } = await axios.post(
            `${API_URL}/api/v1/auth/token/refresh/`,
            { refresh }
          );
          localStorage.setItem("access_token", data.access);
          original.headers.Authorization = `Bearer ${data.access}`;
          return api(original);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      } else {
        window.location.href = "/login";
      }
    }

    return Promise.reject(err);
  }
);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  role: "super_admin" | "owner" | "staff" | "accountant" | "client";
  avatar: string | null;
  is_verified: boolean;
  totp_enabled: boolean;
  timezone_name: string;
  language: string;
  date_joined: string;
  updated_at: string;
}

export interface CompanyBranding {
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  text_color: string;
  background_color: string;
  font_family: string;
  font_size_body: number;
  stamp: string | null;
  signature: string | null;
  invoice_header_text: string;
  invoice_footer_text: string;
  quotation_footer_text: string;
  contract_footer_text: string;
  invoice_terms: string;
  quotation_terms: string;
  updated_at: string;
}

export interface VATConfig {
  vat_number: string;
  vat_registered: boolean;
  vat_rate: string;
  vat_label: string;
  wht_applicable: boolean;
  wht_rate: string;
  wht_label: string;
  extra_tax_label: string;
  extra_tax_rate: string;
  prices_include_tax: boolean;
  show_tax_breakdown: boolean;
  updated_at: string;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  logo_url: string | null;
  email: string;
  phone: string;
  website: string;
  address_line1: string;
  address_line2: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
  full_address: string;
  registration_number: string;
  size: string;
  industry: string;
  currency: string;
  timezone_name: string;
  language: string;
  date_format: string;
  invoice_prefix: string;
  quotation_prefix: string;
  contract_prefix: string;
  next_invoice_number: number;
  next_quotation_number: number;
  next_contract_number: number;
  default_payment_terms: number;
  bank_name: string;
  bank_account_name: string;
  bank_account_number: string;
  bank_branch_code: string;
  swift_code: string;
  iban: string;
  mpesa_paybill: string;
  mpesa_till: string;
  is_active: boolean;
  is_deleted: boolean;
  branding: CompanyBranding | null;
  vat_config: VATConfig | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyMembership {
  id: string;
  company: string;
  user: string;
  user_email: string;
  user_full_name: string;
  role: "owner" | "admin" | "staff" | "accountant" | "client";
  is_active: boolean;
  invited_by: string | null;
  invited_by_email: string | null;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LineItem {
  id?: string;
  item_type: "service" | "product" | "expense" | "discount" | "other";
  description: string;
  quantity: number;
  unit_of_measure: number;
  unit_label: string;
  unit_price: string;
  discount_percent: string;
  tax_rate: string;
  gross_amount?: string;
  discount_value?: string;
  line_total?: string;
  sort_order: number;
  created_at?: string;
}

export interface Invoice {
  id: string;
  company: string;
  client: string | null;
  client_salutation: "Mr" | "Mrs" | "Miss" | "Ms" | "Dr" | "Prof" | "Mx" | "";
  client_name: string | null;
  client_email: string;
  client_phone: string;
  client_address: string;
  client_vat_number: string;
  number: string;
  status: "draft" | "sent" | "viewed" | "partial" | "paid" | "overdue" | "void" | "cancelled";
  currency: string;
  issue_date: string;
  due_date: string | null;
  notes: string;
  terms: string;
  subtotal: string;
  tax_amount: string;
  discount_amount: string;
  total: string;
  amount_paid: string;
  balance_due: string;
  line_items: LineItem[];
  portal_url: string;
  stripe_payment_link_url: string;
  sent_at: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface Contract {
  id: string;
  company: string;
  client: string | null;
  client_salutation: "Mr" | "Mrs" | "Miss" | "Ms" | "Dr" | "Prof" | "Mx" | "";
  client_name: string | null;
  client_email: string;
  client_phone: string;
  client_address: string;
  title: string;
  contract_type: string;
  body: string;
  status: "draft" | "sent" | "viewed" | "pending" | "signed" | "active" | "completed" | "cancelled" | "expired";
  start_date: string | null;
  end_date: string | null;
  auto_renew: boolean;
  renewal_notice_days: number;
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
  client_salutation: "Mr" | "Mrs" | "Miss" | "Ms" | "Dr" | "Prof" | "Mx" | "";
  client_name: string;
  client_email: string;
  client_phone: string;
  client_address: string;
  client_vat_number: string;
  number: string;
  status: "draft" | "sent" | "viewed" | "accepted" | "declined" | "expired";
  currency: string;
  issue_date: string;
  valid_until: string | null;
  notes: string;
  terms: string;
  subtotal: string;
  tax_amount: string;
  discount_amount: string;
  total: string;
  portal_url: string;
  line_items: LineItem[];
}

// ---------------------------------------------------------------------------
// APIs (Strict adherence to trailing slashes matching your backend specs)
// ---------------------------------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    api.post<{ access: string; refresh: string; two_factor_required?: boolean; email?: string }>("/auth/login/", { email, password }),
  verifyTotp: (data: { email: string; token: string }) =>
    api.post<{ access: string; refresh: string }>("/auth/login/verify-totp/", data),
  googleLogin: (accessToken: string) =>
    api.post<{ access: string; refresh: string }>("/auth/google/", { access_token: accessToken }),
  logout: (refresh: string) => api.post("/auth/logout/", { refresh }),
  me: () => api.get<User>("/auth/me/"),
  updateMe: (data: Partial<User>) => api.patch<User>("/auth/me/", data),
  register: (data: { email: string; first_name: string; last_name: string; password: string; password_confirm: string }) =>
    api.post<{ user: User; tokens: { access: string; refresh: string } }>("/auth/register/", data),
  requestPasswordReset: (email: string) => api.post("/auth/password-reset/", { email }),
  confirmPasswordReset: (data: Record<string, string>) => api.post("/auth/password-reset/confirm/", data),
};

export const companiesApi = {
  list: () => api.get<PaginatedResponse<Company>>("/companies/"),
  get: (id: string) => api.get<Company>(`/companies/${id}/`),
  create: (data: Partial<Company>) => api.post<Company>("/companies/", data),
  update: (id: string, data: Partial<Company>) => api.patch<Company>(`/companies/${id}/`, data),
  delete: (id: string) => api.delete(`/companies/${id}/`),
  restore: (id: string) => api.post(`/companies/${id}/restore/`),
  branding: {
    get: (companyId: string) => api.get<CompanyBranding>(`/companies/${companyId}/branding/`),
    update: (companyId: string, data: Partial<CompanyBranding>) => api.patch<CompanyBranding>(`/companies/${companyId}/branding/`, data),
  },
  vat: {
    get: (companyId: string) => api.get<VATConfig>(`/companies/${companyId}/vat/`),
    update: (companyId: string, data: Partial<VATConfig>) => api.patch<VATConfig>(`/companies/${companyId}/vat/`, data),
  },
  members: {
    list: (companyId: string) => api.get<PaginatedResponse<CompanyMembership>>(`/companies/${companyId}/members/`),
    get: (companyId: string, memberId: string) => api.get<CompanyMembership>(`/companies/${companyId}/members/${memberId}/`),
    invite: (companyId: string, data: { email: string; role: string }) => api.post<CompanyMembership>(`/companies/${companyId}/members/invite/`, data),
    updateRole: (companyId: string, memberId: string, data: { role: string; is_active?: boolean }) => api.patch<CompanyMembership>(`/companies/${companyId}/members/${memberId}/role/`, data),
    remove: (companyId: string, memberId: string) => api.delete(`/companies/${companyId}/members/${memberId}/`),
  },
};

export const quotationsApi = {
  list: (params?: Record<string, any>) => api.get<PaginatedResponse<Quotation>>("/documents/quotations/", { params }),
  get: (id: string) => api.get<Quotation>(`/documents/quotations/${id}/`),
  create: (data: Partial<Quotation>) => api.post<Quotation>("/documents/quotations/", data),
  // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
  update: (id: string, data: Partial<Quotation>) => api.patch<Quotation>(`/documents/quotations/${id}/`, data),
  delete: (id: string) => api.delete(`/documents/quotations/${id}/`),
  send: (id: string) => api.post(`/documents/quotations/${id}/send/`),
  accept: (id: string) => api.post(`/documents/quotations/${id}/accept/`),
  decline: (id: string) => api.post(`/documents/quotations/${id}/decline/`),
  convertToInvoice: (id: string) => api.post<{ id: string }>(`/documents/quotations/${id}/convert-to-invoice/`),
  downloadPdf: (id: string) => api.get<{ url: string }>(`/documents/quotations/${id}/download-pdf/`),
};

export const invoicesApi = {
  list: (params?: Record<string, string>) => api.get<PaginatedResponse<Invoice>>("/documents/invoices/", { params }),
  get: (id: string) => api.get<Invoice>(`/documents/invoices/${id}/`),
  create: (data: Partial<Invoice>) => api.post<Invoice>("/documents/invoices/", data),
  // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
  update: (id: string, data: Partial<Invoice>) => api.patch<Invoice>(`/documents/invoices/${id}/`, data),
  delete: (id: string) => api.delete(`/documents/invoices/${id}/`),
  sendEmail: (id: string) => api.post(`/documents/invoices/${id}/send/`),
  markPaid: (id: string) => api.post(`/documents/invoices/${id}/mark-paid/`),
  void: (id: string) => api.post(`/documents/invoices/${id}/void/`),
  downloadPdf: (id: string) => api.get<{ url: string }>(`/documents/invoices/${id}/download-pdf/`),
  downloadDocx: (id: string) => api.get<{ url: string }>(`/documents/invoices/${id}/download-docx/`),
  createPaymentLink: (id: string) => api.post<{ payment_link: string }>(`/billing/invoices/${id}/payment-link/`),
};

export const contractsApi = {
  list: (params?: Record<string, string>) => api.get<PaginatedResponse<Contract>>("/documents/contracts/", { params }),
  get: (id: string) => api.get<Contract>(`/documents/contracts/${id}/`),
  create: (data: Partial<Contract>) => api.post<Contract>("/documents/contracts/", data),
  // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
  update: (id: string, data: Partial<Contract>) => api.patch<Contract>(`/documents/contracts/${id}/`, data),
  delete: (id: string) => api.delete(`/documents/contracts/${id}/`),
  send: (id: string) => api.post(`/documents/contracts/${id}/send/`),
  sign: (id: string, data: { name: string }) => api.post(`/documents/contracts/${id}/sign/`, data),
  downloadPdf: (id: string) => api.get<{ url: string }>(`/documents/contracts/${id}/download-pdf/`),
  aiReview: (id: string) => api.get<{ ai_review: any }>(`/documents/contracts/${id}/ai-review/`),
};

export const aiApi = {
  reviewContract: (formData: FormData) => api.post<AiReview>("/ai/review/", formData, { headers: { "Content-Type": "multipart/form-data" } }),
  listReviews: (companyId?: string) => api.get<AiReview[]>(`/ai/review/${companyId ? `?company=${companyId}` : ""}`),
  generateDocument: (data: { doc_type: string; fields: Record<string, string>; company: string }) => api.post<any>("/ai/generate/", data),
};

export const billingApi = {
  createCheckout: (plan: string) => api.post<{ checkout_url: string }>("/billing/checkout/", { plan }),
  openPortal: () => api.post<{ portal_url: string }>("/billing/portal/"),
};