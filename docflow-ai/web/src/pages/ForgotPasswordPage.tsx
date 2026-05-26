import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { authApi } from "@/lib/api";

const schema = z.object({ email: z.string().email("Invalid email address") });
type Form = z.infer<typeof schema>;

export default function ForgotPassword() {
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");
  const { register, handleSubmit, formState: { errors } } = useForm<Form>({
    resolver: zodResolver(schema)
  });

  const onSubmit = async (data: Form) => {
    setError("");
    try {
      await authApi.requestPasswordReset(data.email);
      setSuccess(true);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to send reset link.");
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
        <div className="max-w-md text-center bg-white p-8 rounded-2xl shadow-sm">
          <h2 className="text-2xl font-bold text-green-600">✅ Check Your Email</h2>
          <p className="mt-4 text-gray-600">We've sent a password reset link.</p>
          <Link to="/login" className="mt-6 inline-block text-indigo-600 hover:underline">Back to Login</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-sm p-8">
        <h1 className="text-2xl font-bold text-center">Forgot Password?</h1>
        <p className="text-center text-gray-500 mt-2">Enter your email to receive a reset link.</p>

        {error && <div className="bg-red-50 text-red-700 p-3 rounded-lg mt-4">{error}</div>}

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4">
          <input
            {...register("email")}
            type="email"
            placeholder="you@company.com"
            className="w-full border border-gray-200 rounded-lg px-4 py-3 focus:ring-2 focus:ring-indigo-500"
          />
          {errors.email && <p className="text-red-500 text-sm">{errors.email.message}</p>}

          <button type="submit" className="w-full bg-indigo-600 text-white py-3 rounded-lg font-medium hover:bg-indigo-700">
            Send Reset Link
          </button>
        </form>

        <p className="text-center mt-6 text-sm">
          <Link to="/login" className="text-indigo-600 hover:underline">Back to Login</Link>
        </p>
      </div>
    </div>
  );
}