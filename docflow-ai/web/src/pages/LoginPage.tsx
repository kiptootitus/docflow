import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FileText, Eye, EyeOff } from "lucide-react";
import { useAuthStore } from "@/lib/auth-store";
import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";
import { authApi } from "@/lib/api";

const schema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

type Form = z.infer<typeof schema>;

export default function LoginPage() {
  const { login, isLoading } = useAuthStore();
  const navigate = useNavigate();

  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [isGoogleLoading, setIsGoogleLoading] = useState(false);

  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: Form) => {
    setError("");
    try {
      await login(data.email, data.password);
      const userResponse = await authApi.me();
      if (userResponse.data.two_factor_enabled) {
        navigate("/verify-2fa");
      } else {
        navigate("/dashboard");
      }
    } catch (err: any) {
      // Pulls structured validation error messages directly from your Django Backend
      if (err.response?.data) {
        const backendData = err.response.data;
        if (backendData.detail) {
          setError(backendData.detail);
        } else if (typeof backendData === "object") {
          // Flatten dictionary errors if fields are returned instead of general detail
          const firstKey = Object.keys(backendData)[0];
          const firstError = backendData[firstKey];
          setError(`${firstKey}: ${Array.isArray(firstError) ? firstError[0] : firstError}`);
        } else {
          setError("Invalid email or password.");
        }
      } else {
        setError("Network error. Could not connect to the authentication server.");
      }
    }
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    setError("");
    setIsGoogleLoading(true);
    try {
      const response = await authApi.googleLogin(credentialResponse.credential);

      localStorage.setItem("access_token", response.data.access);
      localStorage.setItem("refresh_token", response.data.refresh);

      const userResponse = await authApi.me();
      if (userResponse.data.two_factor_enabled) {
        navigate("/verify-2fa");
      } else {
        navigate("/dashboard");
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Google authentication failed. Please try again.");
    } finally {
      setIsGoogleLoading(false);
    }
  };

  const handleGoogleError = () => {
    setError("Google sign in failed. Please try again.");
  };

  return (
    <GoogleOAuthProvider clientId={googleClientId || "13570999136-57i88iqqjsq5vv16339i5jecp1eqvroh.apps.googleusercontent.com"}>
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="text-center mb-8">
            <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-3">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">DocFlow AI</h1>
            <p className="text-gray-500 mt-1">Sign in to your account</p>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-3 mb-4">
                {error}
              </div>
            )}

            <div className="mb-6 flex justify-center w-full">
              <GoogleLogin
                onSuccess={handleGoogleSuccess}
                onError={handleGoogleError}
                theme="outline"
                size="large"
                width="380"
                text="signin_with"
                disabled={isGoogleLoading}
              />
            </div>

            <div className="relative flex py-2 items-center text-xs text-gray-400 uppercase mb-4">
              <div className="flex-grow border-t border-gray-100"></div>
              <span className="flex-shrink mx-4">Or continue with email</span>
              <div className="flex-grow border-t border-gray-100"></div>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  {...register("email")}
                  type="email"
                  placeholder="you@company.com"
                  className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="block text-sm font-medium text-gray-700">Password</label>
                  <Link to="/forgot-password" className="text-xs text-indigo-600 hover:underline">
                    Forgot password?
                  </Link>
                </div>
                <div className="relative">
                  <input
                    {...register("password")}
                    type={showPass ? "text" : "password"}
                    placeholder="••••••••"
                    className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 focus:outline-none"
                  >
                    {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {errors.password && <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>}
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {isLoading ? "Signing in…" : "Sign In"}
              </button>
            </form>

            <p className="text-center text-sm text-gray-500 mt-6">
              Don't have an account?{" "}
              <Link to="/register" className="text-indigo-600 font-medium hover:underline">Sign up</Link>
            </p>
          </div>
        </div>
      </div>
    </GoogleOAuthProvider>
  );
}