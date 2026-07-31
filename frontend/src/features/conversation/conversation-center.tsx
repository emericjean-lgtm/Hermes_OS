"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  useConversationDecision,
  useSendConversationMessage,
  useStartConversation,
} from "@/hooks/use-api";

interface ChatMessage {
  role: "user" | "hermes" | "system" | "agent";
  content: string;
  timestamp: string;
}

interface IntentInfo {
  type: string;
  confidence: number;
  domain: string;
}

interface ConversationResponse {
  success: boolean;
  session_id: string;
  message: { role: string; content: string; timestamp: string };
  intent: IntentInfo | null;
  requires_approval: boolean;
  approval_request: { action: string; risk: string; description: string } | null;
  suggested_actions: { label: string; action: string }[];
  status: string;
}

const WELCOME_MESSAGE: ChatMessage = {
  role: "hermes",
  content:
    "👋 **Bonjour !**\n\nJe suis **Hermes**, votre assistant IA de développement. Je peux vous aider à :\n\n🔍 **Analyser** votre code et vos projets\n⚡ **Optimiser** les performances\n🐛 **Déboguer** les problèmes\n🔄 **Refactoriser** le code\n📝 **Documenter** votre travail\n\nQue souhaitez-vous faire ?",
  timestamp: new Date().toISOString(),
};

export default function ConversationCenter() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<{
    action: string;
    risk: string;
    description: string;
  } | null>(null);
  const [suggestedActions, setSuggestedActions] = useState<
    { label: string; action: string }[]
  >([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startConversation = useStartConversation();
  const sendMessage = useSendConversationMessage();
  const decide = useConversationDecision();

  /** Reuse the live session, opening one on first use. */
  const ensureSession = useCallback(async () => {
    if (sessionId) return sessionId;
    const started = await startConversation.mutateAsync(undefined);
    setSessionId(started.session_id);
    return started.session_id;
  }, [sessionId, startConversation]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = useCallback(async () => {
    if (!input.trim() || isProcessing) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsProcessing(true);
    setError(null);

    try {
      const id = await ensureSession();
      const response = await sendMessage.mutateAsync({
        sessionId: id,
        message: userMsg.content,
      });

      setMessages((prev) => [...prev, {
        role: "hermes",
        content: response.message.content,
        timestamp: response.message.timestamp,
      }]);
      setPendingApproval(response.approval_request);
      setSuggestedActions(response.suggested_actions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Hermes could not be reached");
    } finally {
      setIsProcessing(false);
    }
  }, [input, isProcessing, ensureSession, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleApprove = useCallback(async () => {
    const msg: ChatMessage = {
      role: "user",
      content: "Oui, j'approuve.",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, msg]);
    setPendingApproval(null);
    setIsProcessing(true);
    setError(null);

    try {
      const id = await ensureSession();
      const response = await decide.mutateAsync({ sessionId: id, decision: "approve" });
      setMessages((prev) => [...prev, {
        role: "hermes",
        content: response.message.content,
        timestamp: response.message.timestamp,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Approval could not be recorded");
    } finally {
      setIsProcessing(false);
    }
  }, [ensureSession, decide]);

  const handleReject = useCallback(async () => {
    const msg: ChatMessage = {
      role: "user",
      content: "Non, annule.",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, msg]);
    setPendingApproval(null);
    setIsProcessing(true);
    setError(null);

    try {
      const id = await ensureSession();
      const response = await decide.mutateAsync({ sessionId: id, decision: "cancel" });
      setMessages((prev) => [...prev, {
        role: "hermes",
        content: response.message.content,
        timestamp: response.message.timestamp,
      }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cancellation could not be recorded");
    } finally {
      setIsProcessing(false);
    }
  }, [ensureSession, decide]);

  const displayContent = (content: string) => {
    // Simple markdown-like rendering
    return content
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, "<br/>");
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
        <div className="w-3 h-3 rounded-full bg-cyan-400 animate-pulse" />
        <div>
          <h1 className="text-lg font-semibold text-white">Assistant Hermes</h1>
          <p className="text-xs text-gray-400">
            Session active · {messages.length} messages
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-gray-500 bg-gray-800/60 px-2 py-1 rounded">
            {sessionId ? sessionId.slice(0, 16) + "…" : "no session yet"}
          </span>
        </div>
      </div>

      {/* A failed call must be visible, not silently swallowed. */}
      {error && (
        <div className="mx-6 mt-3 px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                msg.role === "user"
                  ? "bg-cyan-500/20 text-cyan-100 border border-cyan-500/30"
                  : msg.role === "system"
                  ? "bg-yellow-500/10 text-yellow-200 border border-yellow-500/20"
                  : "bg-gray-800/80 text-gray-200 border border-gray-700"
              }`}
            >
              <div
                className="text-sm leading-relaxed prose prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: displayContent(msg.content) }}
              />
              <div className="text-[10px] text-gray-500 mt-2 font-mono">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}

        {isProcessing && (
          <div className="flex justify-start">
            <div className="bg-gray-800/80 border border-gray-700 rounded-2xl px-5 py-3">
              <div className="flex gap-1.5">
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce delay-100" />
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce delay-200" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Approval Banner */}
      {pendingApproval && (
        <div className="mx-6 mb-4 bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
          <div className="flex items-start gap-3">
            <span className="text-xl">🔔</span>
            <div className="flex-1">
              <div className="text-yellow-300 font-medium text-sm">
                Action nécessitant votre approbation
              </div>
              <div className="text-yellow-200/80 text-xs mt-1">
                {pendingApproval.description}
              </div>
              <div className="flex items-center gap-3 mt-2">
                <span
                  className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                    pendingApproval.risk === "HIGH"
                      ? "bg-red-500/20 text-red-400"
                      : "bg-yellow-500/20 text-yellow-400"
                  }`}
                >
                  Risque : {pendingApproval.risk}
                </span>
              </div>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={handleApprove}
                  className="px-4 py-1.5 bg-green-500/20 text-green-300 rounded-lg text-sm hover:bg-green-500/30 transition-all"
                >
                  ✅ Approuver
                </button>
                <button
                  onClick={handleReject}
                  className="px-4 py-1.5 bg-red-500/20 text-red-300 rounded-lg text-sm hover:bg-red-500/30 transition-all"
                >
                  ❌ Refuser
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Suggested Actions */}
      {suggestedActions.length > 0 && !pendingApproval && (
        <div className="mx-6 mb-4 flex gap-2 flex-wrap">
          {suggestedActions.map((action, i) => (
            <button
              key={i}
              onClick={() => {
                setInput(action.label);
              }}
              className="px-3 py-1.5 bg-gray-800/60 border border-gray-700 text-gray-300 rounded-lg text-xs hover:border-cyan-500/40 hover:text-cyan-300 transition-all"
            >
              {action.label}
            </button>
          ))}
        </div>
      )}

      {/* Input Area */}
      <div className="border-t border-gray-700 px-6 py-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question ou donnez une instruction..."
            disabled={isProcessing}
            className="flex-1 bg-gray-800/60 border border-gray-700 rounded-xl px-5 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500/50 transition-all disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isProcessing}
            className="px-5 py-3 bg-cyan-500/20 text-cyan-300 rounded-xl text-sm font-medium hover:bg-cyan-500/30 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {isProcessing ? (
              <div className="flex gap-1">
                <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" />
                <div className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce delay-100" />
              </div>
            ) : (
              "Envoyer"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
