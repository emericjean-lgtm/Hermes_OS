"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";

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

// Mock storage for conversation state
let mockSessionId = `conv_${Math.random().toString(36).slice(2, 14)}`;

function generateMockResponse(userMessage: string): ConversationResponse {
  const lower = userMessage.toLowerCase();
  let content = "";
  let intent: IntentInfo = { type: "unknown", confidence: 0, domain: "general" };
  let requiresApproval = false;
  let approvalRequest: { action: string; risk: string; description: string } | null = null;
  let suggestedActions: { label: string; action: string }[] = [];

  if (lower.includes("optimise") || lower.includes("performance")) {
    content =
      "🔍 **Analyse d'optimisation détectée**\n\nJ'ai compris que vous souhaitez optimiser votre projet. Je peux lancer une mission complète avec analyse des performances et recommandations.";
    intent = { type: "optimization", confidence: 0.88, domain: "software" };
    suggestedActions = [
      { label: "Lancer optimisation", action: "start_mission" },
      { label: "Analyser d'abord", action: "analyze_first" },
    ];
  } else if (lower.includes("debug") || lower.includes("bug") || lower.includes("erreur")) {
    content =
      "🐛 **Diagnostic de bug en cours**\n\nJ'ai détecté une demande de débogage. Je vais analyser le problème avec Oh My Pi et mes agents d'analyse.";
    intent = { type: "debug", confidence: 0.92, domain: "software" };
    requiresApproval = true;
    approvalRequest = {
      action: "debug_mission",
      risk: "HIGH",
      description: "Lancer une mission de débogage complète",
    };
  } else if (lower.includes("refactor") || lower.includes("restructure")) {
    content =
      "🔄 **Refactoring planifié**\n\nJ'ai compris que vous souhaitez refactoriser votre code. Voulez-vous que je commence par une analyse d'impact ?";
    intent = { type: "refactor", confidence: 0.85, domain: "software" };
    requiresApproval = true;
    approvalRequest = {
      action: "refactor_mission",
      risk: "MEDIUM",
      description: "Planifier une mission de refactoring",
    };
  } else if (lower.includes("analyse") || lower.includes("analyse")) {
    content =
      "📊 **Analyse demandée**\n\nJe lance une analyse de votre projet dans le domaine **software**. Je vais examiner le code, la structure et les performances.";
    intent = { type: "analysis", confidence: 0.9, domain: "software" };
    suggestedActions = [
      { label: "Lancer analyse", action: "start_mission" },
      { label: "Voir détails", action: "show_details" },
    ];
  } else if (lower.includes("hello") || lower.includes("bonjour") || lower.includes("salut")) {
    content = WELCOME_MESSAGE.content;
    intent = { type: "greeting", confidence: 0.95, domain: "general" };
    suggestedActions = [
      { label: "Analyser projet", action: "analyze_project" },
      { label: "Voir missions", action: "list_missions" },
    ];
  } else if (lower.includes("oui") || lower.includes("yes") || lower.includes("approuve")) {
    content = "✅ **Approbation enregistrée**\n\nJ'ai bien pris en compte votre validation. Je poursuis l'exécution du plan.";
    intent = { type: "approval", confidence: 0.95, domain: "general" };
  } else if (lower.includes("non") || lower.includes("annule") || lower.includes("stop")) {
    content = "🛑 **Action annulée**\n\nJ'ai annulé l'opération en cours. N'hésitez pas à me donner de nouvelles instructions.";
    intent = { type: "cancel", confidence: 0.9, domain: "general" };
  } else {
    content =
      "🤔 **Je n'ai pas bien compris**\n\nPouvez-vous reformuler votre demande ? Je peux vous aider à analyser, déboguer, optimiser ou refactoriser du code.";
    intent = { type: "unknown", confidence: 0.3, domain: "general" };
  }

  return {
    success: true,
    session_id: mockSessionId,
    message: { role: "hermes", content, timestamp: new Date().toISOString() },
    intent,
    requires_approval: requiresApproval,
    approval_request: approvalRequest,
    suggested_actions: suggestedActions,
    status: requiresApproval ? "awaiting_approval" : "active",
  };
}

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

    // Simulate response delay
    await new Promise((r) => setTimeout(r, 800 + Math.random() * 600));

    const response = generateMockResponse(userMsg.content);

    const hermesMsg: ChatMessage = {
      role: "hermes",
      content: response.message.content,
      timestamp: response.message.timestamp,
    };
    setMessages((prev) => [...prev, hermesMsg]);
    setPendingApproval(response.approval_request);
    setSuggestedActions(response.suggested_actions);
    setIsProcessing(false);
  }, [input, isProcessing]);

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

    await new Promise((r) => setTimeout(r, 500));
    const response: ChatMessage = {
      role: "hermes",
      content:
        "✅ **Approbation enregistrée**\n\nMission en cours d'exécution. Je vous tiendrai informé de la progression.",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, response]);
    setIsProcessing(false);
  }, []);

  const handleReject = useCallback(async () => {
    const msg: ChatMessage = {
      role: "user",
      content: "Non, annule.",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, msg]);
    setPendingApproval(null);
    setIsProcessing(true);

    await new Promise((r) => setTimeout(r, 500));
    const response: ChatMessage = {
      role: "hermes",
      content:
        "🛑 **Action annulée**\n\nJ'ai annulé l'opération. N'hésitez pas à me donner de nouvelles instructions.",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, response]);
    setIsProcessing(false);
  }, []);

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
            {mockSessionId.slice(0, 16)}...
          </span>
        </div>
      </div>

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
