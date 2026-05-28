import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "@/lib/api";
import { Eye, EyeOff } from "lucide-react";

const schema = z.object({
  password: z.string().min(8, "Password must be at least 8 characters long"),
  passwordConfirm: z.string()
}).refine((data) => data.password === data.passwordConfirm, {
  message: "Passwords do not match",
  path: ["passwordConfirm"],
});

type Form = z.infer<typeof schema>;

export default function ResetPasswordConfirmPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema)
  });

  const onSubmit = async (data: Form) => {
    if (!token) {
      setError("Reset token is missing from the link URL.");
      return;
    }
    
    setError("");
    setLoading(true);
    try {
      await authApi.confirmPasswordReset(token, data.password);
      setSuccess(true);
    } catch (err: any) {
      setError(err.response?.data?.token?.[0] || err.response?.data?.detail || "Failed to update password.");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
        <div className="max-w-md text-center bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-2xl font-bold text-red-600">❌ Invalid Reset Link</h2>
          <p className="mt-4 text-gray-600">This password reset confirmation link is missing its authentication token descriptor.</p>
          <Link to="/login" className="mt-6 inline-block text-indigo-600 hover:underline">Back to Login</Link>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
        <div className="max-w-md text-center bg-white p-8 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-2xl font-bold text-green-600">🎉 Password Updated</h2>
          <p className="mt-4 text-gray-600">Your password has been changed successfully. You can now use your new password to sign in.</p>
          <Link to="/login" className="mt-6 inline-block bg-indigo-600 text-white px-6 py-2.5 rounded-lg font-medium hover:bg-indigo-700">
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
        <h1 className="text-2xl font-bold text-center text-gray-900">Set New Password</h1>
        <p className="text-center text-gray-500 mt-2 text-sm">Please choose a strong, secure password containing uppercase, lowercase, numbers, and special characters.</p>

        {error && <div className="bg-red-50 text-red-700 p-3 rounded-lg mt-4 text-sm">{error}</div>}

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
            <div className="relative">
              <input
                {...register("password")}
                type={showPass ? "text" : "password"}
                disabled={loading}
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

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
            <input
              {...register("passwordConfirm")}
              type="password"
              disabled={loading}
              placeholder="••••••••"
              className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {errors.passwordConfirm && <p className="text-red-500 text-xs mt-1">{errors.passwordConfirm.message}</p>}
          </div>

          <button 
            type="submit" 
            disabled={loading}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            {loading ? "Updating Password..." : "Reset Password"}
          </button>
        </form>
      </div>
    </div>
  );
}
