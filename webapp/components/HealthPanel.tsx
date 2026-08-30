"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheck, CircleX, RefreshCw, Loader2 } from "lucide-react";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getHealth } from "@/lib/api";
import type { HealthResponse, ServiceStatus } from "@/lib/types";

function LatencyChart({ data }: { data: HealthResponse }) {
  const rows = data.services
    .filter((s) => s.latency_ms != null)
    .map((s) => ({
      name: s.name,
      latency: s.latency_ms as number,
      ok: s.ok,
    }))
    .sort((a, b) => b.latency - a.latency);

  if (rows.length === 0) return null;

  return (
    <div style={{ height: Math.max(70, rows.length * 26) }} className="mb-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={rows}
          margin={{ top: 4, right: 40, bottom: 4, left: 0 }}
          barCategoryGap={4}
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={72}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
            className="capitalize"
          />
          <Tooltip
            formatter={(value) => `${Number(value).toFixed(0)} ms`}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          />
          <Bar dataKey="latency" radius={4} maxBarSize={14}>
            {rows.map((r, i) => (
              <Cell key={i} fill={r.ok ? "#22c55e" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ServiceRow({ svc }: { svc: ServiceStatus }) {
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        {svc.ok ? (
          <CircleCheck className="w-4 h-4 text-green-500" />
        ) : (
          <CircleX className="w-4 h-4 text-red-500" />
        )}
        <span className="text-sm font-medium capitalize">{svc.name}</span>
        {!svc.ok && svc.error && (
          <span className="text-xs text-muted-foreground truncate max-w-[200px]">
            — {svc.error}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {svc.latency_ms != null && (
          <span className="text-xs font-mono text-muted-foreground">
            {svc.latency_ms.toFixed(0)} ms
          </span>
        )}
        <Badge
          variant="outline"
          className={
            svc.ok
              ? "border-green-500 text-green-600"
              : "border-red-500 text-red-600"
          }
        >
          {svc.ok ? "OK" : "DOWN"}
        </Badge>
      </div>
    </div>
  );
}

export function HealthPanel() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 300_000,
  });

  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            Service Health
            {data && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  data.healthy
                    ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                    : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                }`}
              >
                {data.healthy ? "Healthy" : "Degraded"}
              </span>
            )}
          </CardTitle>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading && (
          <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Checking services…</span>
          </div>
        )}

        {isError && (
          <p className="text-sm text-destructive text-center py-4">
            Could not reach the API. Is the backend running?
          </p>
        )}

        {data && (
          <>
            <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
              Latency
            </p>
            <LatencyChart data={data} />
            <Separator className="mb-1" />
            <div className="divide-y">
              {data.services.map((svc) => (
                <ServiceRow key={svc.name} svc={svc} />
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
