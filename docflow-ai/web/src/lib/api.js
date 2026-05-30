import axios from "axios";
// ---------------------------------------------------------------------------
// Base client
// ---------------------------------------------------------------------------
const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
export const api = axios.create({
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
api.interceptors.response.use((res) => res, async (err) => {
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
            }
            catch {
                localStorage.removeItem("access_token");
                localStorage.removeItem("refresh_token");
                window.location.href = "/login";
            }
        }
        else {
            window.location.href = "/login";
        }
    }
    return Promise.reject(err);
});
// ---------------------------------------------------------------------------
// APIs (Strict adherence to trailing slashes matching your backend specs)
// ---------------------------------------------------------------------------
export const authApi = {
    login: (email, password) => api.post("/auth/login/", { email, password }),
    verifyTotp: (data) => api.post("/auth/login/verify-totp/", data),
    googleLogin: (accessToken) => api.post("/auth/google/", { access_token: accessToken }),
    logout: (refresh) => api.post("/auth/logout/", { refresh }),
    me: () => api.get("/auth/me/"),
    updateMe: (data) => api.patch("/auth/me/", data),
    register: (data) => api.post("/auth/register/", data),
    requestPasswordReset: (email) => api.post("/auth/password-reset/", { email }),
    confirmPasswordReset: (data) => api.post("/auth/password-reset/confirm/", data),
};
export const companiesApi = {
    list: () => api.get("/companies/"),
    get: (id) => api.get(`/companies/${id}/`),
    create: (data) => api.post("/companies/", data),
    update: (id, data) => api.patch(`/companies/${id}/`, data),
    delete: (id) => api.delete(`/companies/${id}/`),
    restore: (id) => api.post(`/companies/${id}/restore/`),
    branding: {
        get: (companyId) => api.get(`/companies/${companyId}/branding/`),
        update: (companyId, data) => api.patch(`/companies/${companyId}/branding/`, data),
    },
    vat: {
        get: (companyId) => api.get(`/companies/${companyId}/vat/`),
        update: (companyId, data) => api.patch(`/companies/${companyId}/vat/`, data),
    },
    members: {
        list: (companyId) => api.get(`/companies/${companyId}/members/`),
        get: (companyId, memberId) => api.get(`/companies/${companyId}/members/${memberId}/`),
        invite: (companyId, data) => api.post(`/companies/${companyId}/members/invite/`, data),
        updateRole: (companyId, memberId, data) => api.patch(`/companies/${companyId}/members/${memberId}/role/`, data),
        remove: (companyId, memberId) => api.delete(`/companies/${companyId}/members/${memberId}/`),
    },
};
export const quotationsApi = {
    list: (params) => api.get("/documents/quotations/", { params }),
    get: (id) => api.get(`/documents/quotations/${id}/`),
    create: (data) => api.post("/documents/quotations/", data),
    // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
    update: (id, data) => api.patch(`/documents/quotations/${id}/`, data),
    delete: (id) => api.delete(`/documents/quotations/${id}/`),
    send: (id) => api.post(`/documents/quotations/${id}/send/`),
    accept: (id) => api.post(`/documents/quotations/${id}/accept/`),
    decline: (id) => api.post(`/documents/quotations/${id}/decline/`),
    convertToInvoice: (id) => api.post(`/documents/quotations/${id}/convert-to-invoice/`),
    downloadPdf: (id) => api.get(`/documents/quotations/${id}/download-pdf/`),
};
export const invoicesApi = {
    list: (params) => api.get("/documents/invoices/", { params }),
    get: (id) => api.get(`/documents/invoices/${id}/`),
    create: (data) => api.post("/documents/invoices/", data),
    // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
    update: (id, data) => api.patch(`/documents/invoices/${id}/`, data),
    delete: (id) => api.delete(`/documents/invoices/${id}/`),
    sendEmail: (id) => api.post(`/documents/invoices/${id}/send/`),
    markPaid: (id) => api.post(`/documents/invoices/${id}/mark-paid/`),
    void: (id) => api.post(`/documents/invoices/${id}/void/`),
    downloadPdf: (id) => api.get(`/documents/invoices/${id}/download-pdf/`),
    downloadDocx: (id) => api.get(`/documents/invoices/${id}/download-docx/`),
    createPaymentLink: (id) => api.post(`/billing/invoices/${id}/payment-link/`),
};
export const contractsApi = {
    list: (params) => api.get("/documents/contracts/", { params }),
    get: (id) => api.get(`/documents/contracts/${id}/`),
    create: (data) => api.post("/documents/contracts/", data),
    // Fixed: Injected standard body payload to prevent update mutations from dropping fields context
    update: (id, data) => api.patch(`/documents/contracts/${id}/`, data),
    delete: (id) => api.delete(`/documents/contracts/${id}/`),
    send: (id) => api.post(`/documents/contracts/${id}/send/`),
    sign: (id, data) => api.post(`/documents/contracts/${id}/sign/`, data),
    downloadPdf: (id) => api.get(`/documents/contracts/${id}/download-pdf/`),
    aiReview: (id) => api.get(`/documents/contracts/${id}/ai-review/`),
};
export const aiApi = {
    reviewContract: (formData) => api.post("/ai/review/", formData, { headers: { "Content-Type": "multipart/form-data" } }),
    listReviews: (companyId) => api.get(`/ai/review/${companyId ? `?company=${companyId}` : ""}`),
    generateDocument: (data) => api.post("/ai/generate/", data),
};
export const billingApi = {
    createCheckout: (plan) => api.post("/billing/checkout/", { plan }),
    openPortal: () => api.post("/billing/portal/"),
};
