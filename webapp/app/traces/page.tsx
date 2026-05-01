"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getTrace, listTraces } from "@/lib/api";
import { MetricsCard } from "@/components/MetricsCard";
import { StateFlowTable } from "@/components/StateFlowTable";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import type { RunStatus, TraceSummary } from "@/lib/types";

const STATUS_BADGE: Record<RunStatus, string> = {
  success: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  error:   "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  timeout: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  blocked: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

export default function TracesPage() {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["traces", page, statusFilter],
    queryFn: () => listTraces({ page, page_size: 20, status: statusFilter }),
  });

  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["trace", selectedId],
    queryFn: () => getTrace(selectedId!),
    enabled: !!selectedId,
  });

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-8rem)]">
      {/* Left — trace list */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">
            Traces {data && <span className="text-muted-foreground font-normal">({data.total} total)</span>}
          </h2>
          <div className="flex gap-1">
            {(["success", "error", "timeout", "blocked"] as RunStatus[]).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(statusFilter === s ? undefined : s)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                  statusFilter === s
                    ? STATUS_BADGE[s] + " border-transparent"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <ScrollArea className="flex-1 border rounded-xl">
          {isLoading && (
            <div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Loading traces…</span>
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive text-center py-8">
              Failed to load traces. Is the backend running?
            </p>
          )}
          {data && (
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead className="w-28">Time</TableHead>
                  <TableHead className="w-20">Status</TableHead>
                  <TableHead>Query</TableHead>
                  <TableHead className="w-20 text-right">ms</TableHead>
                  <TableHead className="w-20 text-right">Tokens</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.traces.map((trace: TraceSummary) => (
                  <TableRow
                    key={trace.request_id}
                    className={`cursor-pointer text-xs transition-colors ${
                      selectedId === trace.request_id ? "bg-muted" : "hover:bg-muted/50"
                    }`}
                    onClick={() => setSelectedId(trace.request_id)}
                  >
                    <TableCell className="font-mono text-muted-foreground">
                      {new Date(trace.timestamp).toLocaleTimeString()}
                    </TableCell>
                    <TableCell>
                      <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${STATUS_BADGE[trace.status as RunStatus]}`}>
                        {trace.status}
                      </span>
                    </TableCell>
                    <TableCell className="truncate max-w-[180px] text-muted-foreground">
                      {trace.query}
                    </TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">
                      {trace.response_time_ms.toFixed(0)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">
                      {trace.total_tokens.toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </ScrollArea>

        {/* Pagination */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-1">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Right — detail */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        {!selectedId ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Select a trace to view details.
          </div>
        ) : detailLoading ? (
          <div className="flex items-center justify-center h-full text-muted-foreground gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Loading…</span>
          </div>
        ) : detail ? (
          <Tabs defaultValue="metrics">
            <TabsList className="w-full">
              <TabsTrigger value="metrics" className="flex-1">Metrics</TabsTrigger>
              <TabsTrigger value="flow" className="flex-1">State Flow</TabsTrigger>
            </TabsList>
            <TabsContent value="metrics" className="mt-4">
              <MetricsCard result={detail} />
            </TabsContent>
            <TabsContent value="flow" className="mt-4">
              <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">
                State Flow — {detail.state_flow.length} steps
              </p>
              <StateFlowTable steps={detail.state_flow} />
            </TabsContent>
          </Tabs>
        ) : null}
      </div>
    </div>
  );
}
