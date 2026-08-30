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
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
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

const TOKEN_COLORS = { input: "#3b82f6", output: "#6366f1", cached: "#22c55e" };
const COST_COLORS = { input: "#3b82f6", output: "#6366f1", cached: "#22c55e" };

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
          {usage.total_tokens > 0 ? (
            <div className="flex items-center gap-4">
              <div className="h-[110px] w-[110px] shrink-0 relative">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={[
                        { name: "Input", value: usage.input_tokens },
                        { name: "Output", value: usage.output_tokens },
                        { name: "Cached", value: usage.cached_tokens },
                      ].filter((d) => d.value > 0)}
                      dataKey="value"
                      nameKey="name"
                      innerRadius="62%"
                      outerRadius="100%"
                      paddingAngle={2}
                      stroke="none"
                    >
                      {[TOKEN_COLORS.input, TOKEN_COLORS.output, TOKEN_COLORS.cached].map(
                        (color) => (
                          <Cell key={color} fill={color} />
                        )
                      )}
                    </Pie>
                    <Tooltip
                      formatter={(value) => Number(value).toLocaleString()}
                      contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <span className="text-sm font-mono font-semibold">
                    {usage.total_tokens.toLocaleString()}
                  </span>
                  <span className="text-[10px] text-muted-foreground">total</span>
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                {[
                  { label: "Input", value: usage.input_tokens, color: TOKEN_COLORS.input },
                  { label: "Output", value: usage.output_tokens, color: TOKEN_COLORS.output },
                  { label: "Cached", value: usage.cached_tokens, color: TOKEN_COLORS.cached },
                ].map(({ label, value, color }) => (
                  <div key={label} className="flex items-center gap-2 text-xs">
                    <span
                      className="w-2 h-2 rounded-sm shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-muted-foreground w-12">{label}</span>
                    <span className="font-mono">{value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No tokens recorded.</p>
          )}
        </div>

        <Separator />

        {/* Cost breakdown */}
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
            Cost Breakdown (USD)
          </p>
          <div className="h-[92px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                layout="vertical"
                data={[
                  { label: "Input", value: cost.input_cost_usd, color: COST_COLORS.input },
                  { label: "Output", value: cost.output_cost_usd, color: COST_COLORS.output },
                  { label: "Cached", value: cost.cached_cost_usd, color: COST_COLORS.cached },
                ]}
                margin={{ top: 0, right: 8, bottom: 0, left: 0 }}
                barCategoryGap={6}
              >
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={48}
                  tickLine={false}
                  axisLine={false}
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                />
                <Tooltip
                  formatter={(value) => `$${Number(value).toFixed(6)}`}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                />
                <Bar dataKey="value" radius={4} maxBarSize={14}>
                  {[COST_COLORS.input, COST_COLORS.output, COST_COLORS.cached].map((color) => (
                    <Cell key={color} fill={color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-between text-xs pt-1 border-t mt-1">
            <span className="text-muted-foreground">Total</span>
            <span className="font-mono font-semibold">${cost.total_cost_usd.toFixed(6)}</span>
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
