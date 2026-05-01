"use client";

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChatPanel } from "@/components/ChatPanel";
import { MetricsCard } from "@/components/MetricsCard";
import { StateFlowTable } from "@/components/StateFlowTable";
import type { QueryResponse } from "@/lib/types";

const DEFAULT_USER = "alice";
const DEFAULT_SESSION = "default";

export default function ChatPage() {
  const [lastResult, setLastResult] = useState<QueryResponse | null>(null);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-8rem)]">
      {/* Left — chat */}
      <ChatPanel
        userId={DEFAULT_USER}
        sessionId={DEFAULT_SESSION}
        onResult={setLastResult}
      />

      {/* Right — metrics */}
      <div className="flex flex-col gap-4 overflow-y-auto">
        {!lastResult ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            Metrics will appear here after the first response.
          </div>
        ) : (
          <Tabs defaultValue="metrics">
            <TabsList className="w-full">
              <TabsTrigger value="metrics" className="flex-1">Metrics</TabsTrigger>
              <TabsTrigger value="flow" className="flex-1">State Flow</TabsTrigger>
            </TabsList>
            <TabsContent value="metrics" className="mt-4">
              <MetricsCard result={lastResult} />
            </TabsContent>
            <TabsContent value="flow" className="mt-4">
              <p className="text-xs text-muted-foreground mb-2 font-medium uppercase tracking-wide">
                State Flow — {lastResult.state_flow.length} steps
              </p>
              <StateFlowTable steps={lastResult.state_flow} />
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
}
