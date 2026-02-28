import { useState, useRef, useEffect } from "react";
import { useCouncilStore } from "@/stores/councilStore";
import { AgentResponse } from "./AgentResponse";
import { StreamingIndicator } from "./StreamingIndicator";
import { cn } from "@/lib/utils";

type QueryMode = "simple" | "council" | "critique";

export function CouncilChat() {
  const [input, setInput] = useState("");
  const [queryMode, setQueryMode] = useState<QueryMode>("simple");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const {
    messages,
    isQuerying,
    streamingContent,
    activeAgents,
    submitQuery,
    submitStreamingQuery,
  } = useCouncilStore();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isQuerying) return;

    const query = input.trim();
    setInput("");

    if (queryMode === "council") {
      submitStreamingQuery(query, "council");
    } else {
      submitQuery(query, queryMode === "critique" ? "analysis" : undefined);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-slate-500 py-16">
            <p className="text-lg mb-2">AI Council</p>
            <p className="text-sm">
              Ask questions, request analysis, or invoke the full council
            </p>
          </div>
        )}

        {messages.map((message) => (
          <div
            key={message.id}
            className={cn(
              "max-w-3xl",
              message.role === "user" ? "ml-auto" : "mr-auto"
            )}
          >
            {message.role === "user" ? (
              <div className="bg-blue-600/20 border border-blue-500/30 rounded-lg px-4 py-3">
                <p className="text-sm text-slate-200">{message.content}</p>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="bg-surface-raised border border-border rounded-lg px-4 py-3">
                  <p className="text-sm text-slate-200 whitespace-pre-wrap">
                    {message.content}
                  </p>
                  {message.confidence !== undefined && (
                    <div className="mt-2 text-xs text-slate-500">
                      Confidence: {Math.round(message.confidence * 100)}%
                    </div>
                  )}
                </div>

                {message.agentOutputs && message.agentOutputs.length > 0 && (
                  <div className="space-y-2 pl-3 border-l-2 border-border">
                    {message.agentOutputs.map((output, i) => (
                      <AgentResponse key={i} output={output} />
                    ))}
                  </div>
                )}

                {message.citations && message.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 text-xs">
                    {message.citations.map((citation, i) => (
                      <span
                        key={i}
                        className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 cursor-pointer hover:text-slate-200"
                        title={citation}
                      >
                        [{i + 1}]
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {/* Streaming content */}
        {streamingContent && (
          <div className="max-w-3xl mr-auto">
            <div className="bg-surface-raised border border-border rounded-lg px-4 py-3">
              <p className="text-sm text-slate-200 whitespace-pre-wrap">
                {streamingContent}
                <span className="animate-pulse">|</span>
              </p>
            </div>
          </div>
        )}

        {/* Active agents */}
        {activeAgents.size > 0 && <StreamingIndicator agents={activeAgents} />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-border p-4">
        <div className="flex gap-2 mb-2">
          {(["simple", "council", "critique"] as QueryMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setQueryMode(mode)}
              className={cn(
                "px-2 py-0.5 text-xs rounded transition-colors",
                queryMode === mode
                  ? "bg-blue-500/20 text-blue-400"
                  : "text-slate-500 hover:text-slate-300"
              )}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              queryMode === "critique"
                ? "Enter a statement to critique..."
                : "Ask the AI Council..."
            }
            rows={2}
            className="flex-1 px-3 py-2 text-sm bg-surface border border-border rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 resize-none"
          />
          <button
            type="submit"
            disabled={isQuerying || !input.trim()}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed self-end"
          >
            {isQuerying ? "..." : "Send"}
          </button>
        </form>
        <span className="text-xs text-slate-500 mt-1 block">
          Cmd+Enter to send
        </span>
      </div>
    </div>
  );
}
