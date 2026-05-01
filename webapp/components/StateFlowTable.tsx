"use client";

import { User, Bot, Wrench, ArrowUpFromLine } from "lucide-react";
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
  { icon: React.ReactNode; label: string; badge: string }
> = {
  user_message: {
    icon: <User className="w-3.5 h-3.5" />,
    label: "User",
    badge: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
  },
  llm_response: {
    icon: <Bot className="w-3.5 h-3.5" />,
    label: "LLM",
    badge: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  },
  tool_call: {
    icon: <Wrench className="w-3.5 h-3.5" />,
    label: "Tool Call",
    badge: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  },
  tool_result: {
    icon: <ArrowUpFromLine className="w-3.5 h-3.5" />,
    label: "Tool Result",
    badge: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  },
};

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
  );
}
