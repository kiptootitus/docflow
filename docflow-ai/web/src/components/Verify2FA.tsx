import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "@/lib/api";

export default function Verify2FA() {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleVerify = async () => {
    try {
      await authApi.verify2FA(code);
      navigate("/dashboard");
    } catch (err: any) {
      setError("Invalid code. Please try again.");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 to-white flex items-center justify-center">
      <div className="bg-white p-8 rounded-2xl shadow-sm w-full max-w-md">
        <h2 className="text-2xl font-bold text-center">Two-Factor Authentication</h2>
        <p className="text-center text-gray-500 mt-2">Enter the code from your authenticator app</p>

        {error && <div className="bg-red-50 text-red-700 p-3 rounded mt-4">{error}</div>}

        <input
          type="text"
          maxLength={6}
          value={code}
          onChange={(e) => setCode(e.target.value)}
          className="w-full text-center text-4xl tracking-widest border border-gray-200 rounded-lg py-4 mt-6"
          placeholder="123456"
        />

        <button
          onClick={handleVerify}
          className="w-full bg-indigo-600 text-white py-3 rounded-lg mt-6 font-medium"
        >
          Verify
        </button>

        <p className="text-center text-sm text-gray-500 mt-6">
          Lost access? Use a <button className="text-indigo-600">backup code</button>
        </p>
      </div>
    </div>
  );
}