"use client";

import {
  Clock,
  Brain,
  Wrench,
  CircleCheck,
  CircleX,
  Timer,
  Ban,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { QueryResponse, RunStatus, StepType } from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_ICON: Record<RunStatus, React.ReactNode> = {
  success: <CircleCheck className="w-4 h-4 text-green-500" />,
  error:   <CircleX   className="w-4 h-4 text-red-500" />,
  timeout: <Timer     className="w-4 h-4 text-yellow-500" />,
  blocked: <Ban       className="w-4 h-4 text-purple-500" />,
};

const STATUS_BADGE: Record<RunStatus, string> = {
  success: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  error:   "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  timeout: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  blocked: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

const BAR_WIDTH = 80; // px

function TokenBar({
  value,
  total,
  color,
}: {
  value: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  const width = total > 0 ? Math.round((value / total) * BAR_WIDTH) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 rounded-full bg-muted overflow-hidden" style={{ width: BAR_WIDTH }}>
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${color}`}
          style={{ width }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-8">{pct}%</span>
    </div>
  );
}

function StatPill({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-2 rounded-lg bg-muted/40 min-w-[80px]">
      <div className="text-muted-foreground">{icon}</div>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold">{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface MetricsCardProps {
  result: QueryResponse;
}

export function MetricsCard({ result }: MetricsCardProps) {
  const { usage, cost, state_flow, status, response_time_ms, model, request_id, timestamp } = result;

  const llmCalls  = state_flow.filter((s) => s.step_type === "llm_response").length;
  const toolCalls = state_flow.filter((s) => s.step_type === "tool_call").length;
  const modelShort = model.split(":").pop() ?? model;

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            Request Metrics
            <span className="text-xs font-mono text-muted-foreground">{request_id}</span>
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{modelShort}</Badge>
            <span
              className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[status]}`}
            >
              {STATUS_ICON[status]}
              {status.toUpperCase()}
            </span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {new Date(timestamp).toLocaleString()} · {result.user_id}
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Summary pills */}
        <div className="flex flex-wrap gap-2">
          <StatPill
            icon={<Clock className="w-4 h-4" />}
            label="Time"
            value={`${response_time_ms.toLocaleString()} ms`}
          />
          <StatPill
            icon={<Brain className="w-4 h-4" />}
            label="LLM Calls"
            value={String(llmCalls)}
          />
          <StatPill
            icon={<Wrench className="w-4 h-4" />}
            label="Tool Calls"
            value={String(toolCalls)}
          />
          <StatPill
            icon={<span className="text-sm font-bold">Σ</span>}
            label="Tokens"
            value={usage.total_tokens.toLocaleString()}
          />
          <StatPill
            icon={<span className="text-sm font-bold">$</span>}
            label="Cost"
            value={`$${cost.total_cost_usd.toFixed(5)}`}
          />
        </div>

        <Separator />

        {/* Token usage */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
            Token Usage
          </p>
          <div className="space-y-2">
            {[
              { label: "Input",  value: usage.input_tokens,  total: usage.total_tokens, color: "bg-blue-500" },
              { label: "Output", value: usage.output_tokens, total: usage.total_tokens, color: "bg-indigo-500" },
              { label: "Cached", value: usage.cached_tokens, total: usage.input_tokens, color: "bg-green-500" },
            ].map(({ label, value, total, color }) => (
              <div key={label} className="flex items-center gap-3">
                <span className="text-xs w-12 text-muted-foreground">{label}</span>
                <TokenBar value={value} total={total} color={color} />
                <span className="text-xs font-mono w-16 text-right">{value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Cost breakdown */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
            Cost Breakdown (USD)
          </p>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            {[
              { label: "Input",  value: cost.input_cost_usd,  color: "text-blue-500" },
              { label: "Output", value: cost.output_cost_usd, color: "text-indigo-500" },
              { label: "Cached", value: cost.cached_cost_usd, color: "text-green-500" },
              { label: "Total",  value: cost.total_cost_usd,  color: "text-foreground font-semibold" },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex justify-between">
                <span className="text-muted-foreground">{label}</span>
                <span className={`font-mono ${color}`}>${value.toFixed(6)}</span>
              </div>
            ))}
          </div>
        </div>

        {result.error && (
          <>
            <Separator />
            <p className="text-xs text-destructive bg-destructive/10 rounded-md px-3 py-2">
              {result.error}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
