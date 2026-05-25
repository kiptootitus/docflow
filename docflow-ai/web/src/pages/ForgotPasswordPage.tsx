import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { FileText, ArrowLeft } from "lucide-react";
import { authApi } from "@/lib/api";

const schema = z.object({ email: z.string().email("Invalid email address") });
type Form = z.infer<typeof schema>;

export default function ForgotPasswordPage() {
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: Form) => {
    setError("");
    setLoading(true);
    try {
      await authApi.requestPasswordReset(data.email);
      setSuccess(true);
    } catch {
      setError("Failed to initiate password reset. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <Link to="/login" className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900 mb-6">
            <ArrowLeft className="w-4 h-4" /> Back to Sign In
          </Link>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Reset Password</h2>
          <p className="text-sm text-gray-500 mb-6">Enter your email and we'll send a link to securely reset your credentials.</p>

          {success ? (
            <div className="bg-emerald-50 text-emerald-700 text-sm rounded-lg p-4">
              If an account exists, a secure authorization reset link has been dispatched to your mailbox.
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3">{error}</div>}
              <div>
                <input {...register("email")} type="email" placeholder="you@company.com" className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
              </div>
              <button type="submit" disabled={loading} className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition-colors disabled:opacity-50">
                {loading ? "Sending link..." : "Send Reset Link"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}