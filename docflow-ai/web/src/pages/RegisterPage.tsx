import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Eye, EyeOff } from "lucide-react";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/lib/auth-store";

export default function RegisterPage() {
  const { setTokens, fetchMe } = useAuthStore();
  const navigate = useNavigate();
  
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  
  // Input tracking
  const [form, setForm] = useState({
    email: "",
    first_name: "",
    last_name: "",
    password: "",
    password_confirm: ""
  });

  // Independent toggle states for password fields
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.password !== form.password_confirm) { 
      setError("Passwords do not match."); 
      return; 
    }
    
    setLoading(true); 
    setError("");
    
    try {
      const { data } = await authApi.register(form);
      setTokens(data.tokens.access, data.tokens.refresh);
      await fetchMe();
      navigate("/dashboard");
    } catch (err: any) {
      if (err.response?.data) {
        const backendErrors = err.response.data;
        
        // Checks if backend returned specific field array validation strings
        if (backendErrors.email) {
          setError(`Email field: ${backendErrors.email[0]}`);
        } else if (backendErrors.password) {
          setError(`Password field: ${backendErrors.password[0]}`);
        } else if (backendErrors.non_field_errors) {
          setError(backendErrors.non_field_errors[0]);
        } else if (typeof backendErrors === "object") {
          const firstKey = Object.keys(backendErrors)[0];
          const firstMsg = backendErrors[firstKey];
          setError(`${firstKey}: ${Array.isArray(firstMsg) ? firstMsg[0] : firstMsg}`);
        } else {
          setError("Registration failed. Please check your network connection.");
        }
      } else {
        setError("Registration failed due to a system network error.");
      }
    } finally { 
      setLoading(false); 
    }
  };

  const handleInputChange = (key: keyof typeof form, value: string) => {
    setForm(p => ({ ...p, [key]: value }));
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-3">
            <FileText className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Create your account</h1>
        </div>
        
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          {error && (
            <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 mb-4">
              {error}
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
                <input 
                  type="text" 
                  value={form.first_name} 
                  onChange={e => handleInputChange("first_name", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" 
                  required 
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                <input 
                  type="text" 
                  value={form.last_name} 
                  onChange={e => handleInputChange("last_name", e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" 
                  required 
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input 
                type="email" 
                value={form.email} 
                onChange={e => handleInputChange("email", e.target.value)}
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" 
                required 
              />
            </div>

            {/* Password input field wrapper with view toggle feature */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <div className="relative">
                <input 
                  type={showPassword ? "text" : "password"} 
                  value={form.password} 
                  onChange={e => handleInputChange("password", e.target.value)}
                  placeholder="At least 8 characters"
                  className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10" 
                  required 
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Password verification input field wrapper with view toggle feature */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password</label>
              <div className="relative">
                <input 
                  type={showConfirmPassword ? "text" : "password"} 
                  value={form.password_confirm} 
                  onChange={e => handleInputChange("password_confirm", e.target.value)}
                  placeholder="Repeat your password"
                  className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10" 
                  required 
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none"
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={loading} 
              className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50 mt-2"
            >
              {loading ? "Creating account…" : "Create Account"}
            </button>
          </form>

          <p className="text-center text-sm text-gray-500 mt-6">
            Already have an account?{" "}
            <Link to="/login" className="text-indigo-600 font-medium hover:underline">Sign in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}