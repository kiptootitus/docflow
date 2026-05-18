import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { Sparkles, Upload, AlertTriangle, CheckCircle, Info, Lightbulb } from "lucide-react";
import { aiApi, companiesApi } from "@/lib/api";
import { formatDate, cn } from "@/lib/utils";
import type { AiReview } from "@/lib/api";

const TYPE_ICONS = {
  risk: { icon: AlertTriangle, color: "text-red-500", bg: "bg-red-50 border-red-100" },
  suggestion: { icon: Lightbulb, color: "text-amber-500", bg: "bg-amber-50 border-amber-100" },
  compliant: { icon: CheckCircle, color: "text-green-500", bg: "bg-green-50 border-green-100" },
  note: { icon: Info, color: "text-blue-500", bg: "bg-blue-50 border-blue-100" },
};

export default function AiReviewPage() {
  const qc = useQueryClient();
  const [selectedReview, setSelectedReview] = useState<AiReview | null>(null);

  const { data: companiesData } = useQuery({ queryKey: ["companies"], queryFn: () => companiesApi.list() });
  const company = companiesData?.data?.results?.[0];

  const { data: reviewsData } = useQuery({
    queryKey: ["ai-reviews"],
    queryFn: () => aiApi.listReviews(company?.id),
    enabled: Boolean(company),
  });
  const reviews = reviewsData?.data ?? [];

  const reviewMutation = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("company", company!.id);
      return aiApi.reviewContract(fd);
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["ai-reviews"] });
      setSelectedReview(res.data);
    },
  });

  const onDrop = useCallback((files: File[]) => {
    if (files[0] && company) reviewMutation.mutate(files[0]);
  }, [company, reviewMutation]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { "application/pdf": [".pdf"] }, maxFiles: 1,
  });

  return (
    <div className="p-8 h-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-indigo-500" /> AI Contract Review
        </h1>
        <p className="text-gray-500 mt-1">Upload a contract PDF to get AI-powered risk analysis and suggestions.</p>
      </div>

      <div className="grid grid-cols-3 gap-6 h-[calc(100%-100px)]">
        {/* Left: Upload + History */}
        <div className="space-y-4">
          {/* Upload */}
          <div
            {...getRootProps()}
            className={cn(
              "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all",
              isDragActive ? "border-indigo-400 bg-indigo-50" : "border-gray-200 hover:border-indigo-300 hover:bg-gray-50",
              reviewMutation.isPending && "opacity-50 pointer-events-none"
            )}
          >
            <input {...getInputProps()} />
            <Upload className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            {reviewMutation.isPending ? (
              <>
                <p className="text-sm font-medium text-indigo-600">Analysing with AI…</p>
                <p className="text-xs text-gray-400 mt-1">This may take 15–30 seconds</p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-gray-700">Drop a contract PDF here</p>
                <p className="text-xs text-gray-400 mt-1">or click to browse</p>
              </>
            )}
          </div>

          {/* History */}
          <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-50">
              <h3 className="text-sm font-semibold text-gray-700">Review History</h3>
            </div>
            <div className="divide-y divide-gray-50">
              {reviews.length === 0 && (
                <p className="px-4 py-6 text-sm text-gray-400 text-center">No reviews yet</p>
              )}
              {reviews.map((r) => (
                <button key={r.id} onClick={() => setSelectedReview(r)}
                  className={cn("w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors", selectedReview?.id === r.id && "bg-indigo-50")}>
                  <p className="text-sm font-medium text-gray-800 truncate">{r.document_name}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium",
                      r.status === "completed" ? "bg-green-100 text-green-700" : r.status === "failed" ? "bg-red-100 text-red-700" : "bg-gray-100 text-gray-600"
                    )}>{r.status}</span>
                    <span className="text-xs text-gray-400">{formatDate(r.created_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Results */}
        <div className="col-span-2 bg-white rounded-xl border border-gray-100 overflow-auto">
          {!selectedReview ? (
            <div className="flex items-center justify-center h-full text-center p-8">
              <div>
                <Sparkles className="w-12 h-12 text-gray-200 mx-auto mb-3" />
                <p className="text-gray-400">Upload a contract to see AI analysis</p>
              </div>
            </div>
          ) : (
            <div className="p-6">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{selectedReview.document_name}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">
                    {selectedReview.review_results.length} findings · {selectedReview.model_used} · {selectedReview.tokens_used.toLocaleString()} tokens
                  </p>
                </div>
                {/* Summary badges */}
                <div className="flex gap-2">
                  {(["risk","suggestion","compliant","note"] as const).map(type => {
                    const count = selectedReview.review_results.filter(r => r.type === type).length;
                    if (!count) return null;
                    const { color } = TYPE_ICONS[type];
                    return <span key={type} className={cn("text-xs font-semibold px-2 py-1 rounded-full bg-gray-100", color)}>{count} {type}</span>;
                  })}
                </div>
              </div>

              <div className="space-y-3">
                {selectedReview.review_results.map((finding, i) => {
                  const { icon: Icon, color, bg } = TYPE_ICONS[finding.type] ?? TYPE_ICONS.note;
                  return (
                    <div key={i} className={cn("border rounded-xl p-4", bg)}>
                      <div className="flex items-start gap-3">
                        <Icon className={cn("w-5 h-5 mt-0.5 flex-shrink-0", color)} />
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-sm font-semibold text-gray-900">{finding.title}</h3>
                            {finding.severity && (
                              <span className={cn("text-xs px-1.5 py-0.5 rounded-full font-medium",
                                finding.severity === "high" ? "bg-red-100 text-red-700" :
                                finding.severity === "medium" ? "bg-amber-100 text-amber-700" :
                                "bg-gray-100 text-gray-600"
                              )}>{finding.severity}</span>
                            )}
                            {finding.clause_reference && (
                              <span className="text-xs text-gray-400">{finding.clause_reference}</span>
                            )}
                          </div>
                          <p className="text-sm text-gray-700">{finding.description}</p>
                          {finding.recommendation && (
                            <p className="text-xs text-gray-500 mt-2 italic">💡 {finding.recommendation}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {selectedReview.status === "failed" && (
                  <div className="text-center py-8 text-red-500">Analysis failed. Please try again.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
