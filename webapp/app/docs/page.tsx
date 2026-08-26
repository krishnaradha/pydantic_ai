"use client";

import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listDocuments, uploadDocument } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { FileText, Upload, Loader2, FileType } from "lucide-react";
import type { DocumentMeta } from "@/lib/types";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  const { data: docs, isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const { mutate: upload, isPending } = useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: (res) => {
      setUploadMsg(res.message);
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err: Error) => setUploadMsg(`Error: ${err.message}`),
  });

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      setUploadMsg(null);
      upload(file);
    }
  }

  return (
    <div className="max-w-2xl mx-auto pt-8 flex flex-col gap-6">
      {/* Upload */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Upload className="w-4 h-4" />
            Upload Document
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-xs text-muted-foreground">
            Supported formats: <Badge variant="outline">.txt</Badge>{" "}
            <Badge variant="outline">.pdf</Badge> — max 20 MB
          </p>
          <div className="flex gap-2 items-center">
            <Button
              variant="outline"
              size="sm"
              disabled={isPending}
              onClick={() => fileRef.current?.click()}
            >
              {isPending ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Upload className="w-4 h-4 mr-2" />
              )}
              {isPending ? "Uploading…" : "Choose File"}
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.pdf"
              className="hidden"
              onChange={handleFile}
            />
            {uploadMsg && (
              <p className={`text-xs ${uploadMsg.startsWith("Error") ? "text-destructive" : "text-green-600"}`}>
                {uploadMsg}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Document list */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Knowledge Base
            {docs && (
              <Badge variant="secondary" className="ml-1">{docs.length} files</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && (
            <div className="flex items-center gap-2 text-muted-foreground py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading…</span>
            </div>
          )}
          {docs && docs.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No documents indexed yet. Upload one above.
            </p>
          )}
          {docs && docs.length > 0 && (
            <div className="divide-y">
              {docs.map((doc: DocumentMeta) => (
                <div key={doc.filename} className="flex items-center justify-between py-2">
                  <div className="flex items-center gap-2">
                    <FileType className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-medium">{doc.filename}</span>
                    <Badge variant="outline" className="text-xs">{doc.suffix}</Badge>
                  </div>
                  <span className="text-xs text-muted-foreground font-mono">
                    {formatBytes(doc.size_bytes)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
