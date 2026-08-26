"use client";

import { useRef, useState } from "react";
import { Send, StopCircle, Trash2, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { clearHistory, streamQuery } from "@/lib/api";
import type { QueryResponse, HistoryMessage } from "@/lib/types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  result?: QueryResponse;
}

interface ChatPanelProps {
  userId: string;
  sessionId?: string;
  initialMessages?: HistoryMessage[];
  onResult?: (result: QueryResponse) => void;
}

export function ChatPanel({
  userId,
  sessionId = "default",
  initialMessages = [],
  onResult,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>(
    initialMessages.map((m, i) => ({
      id: String(i),
      role: m.role,
      content: m.content,
    }))
  );
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stopRef = useRef<(() => void) | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  function scrollToBottom() {
    // ScrollArea renders an internal viewport div — scroll that directly
    const viewport = scrollAreaRef.current?.querySelector("[data-radix-scroll-area-viewport]");
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight;
    } else {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }

  async function handleSend() {
    const query = input.trim();
    if (!query || isStreaming) return;

    setInput("");
    setError(null);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
    };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);
    scrollToBottom();

    const stop = streamQuery(query, userId, sessionId, {
      onChunk(delta) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + delta } : m
          )
        );
        scrollToBottom();
      },
      onDone(result) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: result.final_output ?? m.content, streaming: false, result }
              : m
          )
        );
        setIsStreaming(false);
        onResult?.(result);
        scrollToBottom();
      },
      onError(err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Something went wrong.", streaming: false }
              : m
          )
        );
        setError(err);
        setIsStreaming(false);
      },
    });

    stopRef.current = stop;
  }

  function handleStop() {
    stopRef.current?.();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) =>
        m.streaming ? { ...m, streaming: false } : m
      )
    );
  }

  async function handleClear() {
    await clearHistory(userId, sessionId);
    setMessages([]);
    setError(null);
  }

  return (
    <div className="flex flex-col h-full min-h-0 border rounded-xl overflow-hidden bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-primary" />
          <span className="font-semibold text-sm">Assistant</span>
          <Badge variant="secondary" className="text-xs">{userId}</Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleClear}
          disabled={isStreaming || messages.length === 0}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="w-4 h-4 mr-1" />
          Clear
        </Button>
      </div>

      {/* Messages */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 min-h-0 px-4 py-4">
        <div className="flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm gap-2">
              <Bot className="w-10 h-10 opacity-30" />
              <p>Ask a question to get started.</p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
            >
              {/* Avatar */}
              <div
                className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {msg.role === "user" ? (
                  <User className="w-4 h-4" />
                ) : (
                  <Bot className="w-4 h-4" />
                )}
              </div>

              {/* Bubble */}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-tr-sm"
                    : "bg-muted text-foreground rounded-tl-sm"
                }`}
              >
                {msg.streaming && !msg.content ? (
                  <span className="flex items-center gap-2 text-muted-foreground select-none">
                    <span className="text-xs font-medium tracking-wide">Thinking</span>
                    <span className="flex gap-0.5">
                      <span className="w-1 h-1 rounded-full bg-current animate-bounce [animation-delay:0ms]" />
                      <span className="w-1 h-1 rounded-full bg-current animate-bounce [animation-delay:150ms]" />
                      <span className="w-1 h-1 rounded-full bg-current animate-bounce [animation-delay:300ms]" />
                    </span>
                  </span>
                ) : (
                  <>
                    {msg.content}
                    {msg.streaming && (
                      <span className="inline-block w-1.5 h-4 ml-0.5 bg-current opacity-70 animate-pulse rounded-sm" />
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

          {error && (
            <p className="text-xs text-destructive text-center py-2">{error}</p>
          )}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>

      <Separator />

      {/* Input */}
      <div className="px-4 py-3 flex gap-2 items-end bg-background">
        <textarea
          className="flex-1 resize-none rounded-lg border bg-muted/30 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary min-h-[44px] max-h-[160px]"
          placeholder="Ask a question…"
          rows={1}
          value={input}
          disabled={isStreaming}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        {isStreaming ? (
          <Button size="icon" variant="destructive" onClick={handleStop}>
            <StopCircle className="w-4 h-4" />
          </Button>
        ) : (
          <Button size="icon" onClick={handleSend} disabled={!input.trim()}>
            <Send className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
