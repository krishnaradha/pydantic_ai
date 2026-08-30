"use client";

import { User, Bot, Wrench, ArrowUpFromLine } from "lucide-react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { StateStep, StepType } from "@/lib/types";

// ---------------------------------------------------------------------------
// Step type config
// ---------------------------------------------------------------------------

const STEP_CONFIG: Record<
  StepType,
  { icon: React.ReactNode; label: string; badge: string; hex: string }
> = {
  user_message: {
    icon: <User className="w-3.5 h-3.5" />,
    label: "User",
    badge: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
    hex: "#06b6d4",
  },
  llm_response: {
    icon: <Bot className="w-3.5 h-3.5" />,
    label: "LLM",
    badge: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    hex: "#3b82f6",
  },
  tool_call: {
    icon: <Wrench className="w-3.5 h-3.5" />,
    label: "Tool Call",
    badge: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
    hex: "#eab308",
  },
  tool_result: {
    icon: <ArrowUpFromLine className="w-3.5 h-3.5" />,
    label: "Tool Result",
    badge: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    hex: "#22c55e",
  },
};

// ---------------------------------------------------------------------------
// Timeline chart — duration_ms per step; steps with no recorded duration
// (e.g. user_message) get a hairline marker instead of a bar.
// ---------------------------------------------------------------------------

function StepTimeline({ steps }: { steps: StateStep[] }) {
  // The backend doesn't populate duration_ms on every run yet — showing a
  // chart with a handful of real values mixed into an all-null run would
  // render as a misleading wall of equal-width bars. Only render once every
  // step in this run has a real duration; otherwise the table below (which
  // already renders "—" per null) carries the info alone.
  const allTimed = steps.every((s) => s.duration_ms != null);
  if (!allTimed) return null;

  const data = steps.map((s) => ({
    label: `${s.index}. ${STEP_CONFIG[s.step_type].label}`,
    duration: s.duration_ms as number,
    hex: STEP_CONFIG[s.step_type].hex,
  }));

  const height = Math.max(90, data.length * 26);

  return (
    <div style={{ height }} className="mb-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 4, right: 12, bottom: 4, left: 0 }}
          barCategoryGap={4}
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={100}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10.5, fill: "var(--muted-foreground)" }}
          />
          <Tooltip
            formatter={(value) => `${Number(value).toFixed(0)} ms`}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          />
          <Bar dataKey="duration" radius={3} maxBarSize={12}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.hex} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const PREVIEW_CHARS = 120;

function preview(text: string) {
  return text.length > PREVIEW_CHARS
    ? text.slice(0, PREVIEW_CHARS) + "…"
    : text;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface StateFlowTableProps {
  steps: StateStep[];
}

export function StateFlowTable({ steps }: StateFlowTableProps) {
  if (steps.length === 0) {
    return (
      <p className="text-xs text-muted-foreground text-center py-6">
        No steps recorded.
      </p>
    );
  }

  return (
    <div>
      <StepTimeline steps={steps} />
      <ScrollArea className="max-h-[420px] rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40">
            <TableHead className="w-8 text-center">#</TableHead>
            <TableHead className="w-28">Type</TableHead>
            <TableHead className="w-32">Name</TableHead>
            <TableHead>Preview</TableHead>
            <TableHead className="w-20 text-right">ms</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {steps.map((step) => {
            const cfg = STEP_CONFIG[step.step_type];
            return (
              <TableRow key={step.index} className="align-top text-xs">
                <TableCell className="text-center text-muted-foreground font-mono">
                  {step.index}
                </TableCell>
                <TableCell>
                  <span
                    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cfg.badge}`}
                  >
                    {cfg.icon}
                    {cfg.label}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground font-mono truncate max-w-[120px]">
                  {step.name ?? "—"}
                </TableCell>
                <TableCell className="text-muted-foreground break-all leading-relaxed">
                  {preview(step.content)}
                </TableCell>
                <TableCell className="text-right font-mono text-muted-foreground">
                  {step.duration_ms != null
                    ? `${step.duration_ms.toFixed(0)}`
                    : "—"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      </ScrollArea>
    </div>
  );
}
