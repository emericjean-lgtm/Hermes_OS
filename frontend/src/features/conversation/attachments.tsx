"use client";

import React, { useCallback, useRef } from "react";
import { FileText, Paperclip, X } from "lucide-react";

/**
 * Text/code attachments (HOS-075).
 *
 * Read entirely client-side and folded into the outgoing message as a
 * fenced code block — there is no upload endpoint, no server-side file
 * storage, and `/chat`/`/conversation/stream` accept plain text messages
 * only. Images and archives are deliberately out of scope: nothing in the
 * inference path (`BaseAgent.respond_events`, Ollama's `/api/chat`) accepts
 * vision input today, and a zip has no defined "what happens to its
 * contents" — building either would be a control that lies about what it
 * does.
 */

export const MAX_ATTACHMENT_BYTES = 200 * 1024;

export interface Attachment {
  id: string;
  name: string;
  content: string;
  bytes: number;
}

const ACCEPTED_EXTENSIONS =
  ".txt,.md,.markdown,.json,.yaml,.yml,.toml,.ini,.cfg,.csv,.log," +
  ".py,.js,.jsx,.ts,.tsx,.java,.go,.rs,.c,.h,.cpp,.hpp,.cs,.rb,.php,.sh,.sql,.css,.scss,.html,.xml";

const NUL = String.fromCharCode(0);
const REPLACEMENT_CHAR = "�";

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
}

async function readAsAttachment(file: File): Promise<Attachment> {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    throw new Error(`${file.name} dépasse ${Math.round(MAX_ATTACHMENT_BYTES / 1024)} Ko (${Math.round(file.size / 1024)} Ko) — trop volumineux pour un envoi direct.`);
  }
  const text = await file.text();
  // Binary files decoded as UTF-8 text surface as NUL bytes or the
  // replacement character — a clear refusal beats sending garbage tokens
  // to the model.
  if (text.includes(NUL) || text.includes(REPLACEMENT_CHAR)) {
    throw new Error(`${file.name} ne ressemble pas à un fichier texte — seuls le texte et le code sont acceptés.`);
  }
  return { id: `a_${Math.random().toString(36).slice(2, 10)}`, name: file.name, content: text, bytes: file.size };
}

/** Turns pending attachments into the fenced-code preamble prepended to the
 *  outgoing message — the model sees exactly what the chip promised. */
export function buildAttachmentPreamble(attachments: Attachment[]): string {
  if (attachments.length === 0) return "";
  return attachments
    .map((a) => `\`\`\`${extensionOf(a.name)}\n// ${a.name}\n${a.content}\n\`\`\``)
    .join("\n\n") + "\n\n";
}

export function AttachButton({
  onFiles, onError,
}: {
  onFiles: (attachments: Attachment[]) => void;
  onError: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow re-selecting the same file later
    const results: Attachment[] = [];
    for (const file of files) {
      try {
        results.push(await readAsAttachment(file));
      } catch (err) {
        onError(err instanceof Error ? err.message : `Impossible de lire ${file.name}.`);
      }
    }
    if (results.length > 0) onFiles(results);
  }, [onFiles, onError]);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_EXTENSIONS}
        className="hidden"
        onChange={(e) => void handleChange(e)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        title="Joindre un fichier texte ou de code"
        className="flex items-center gap-1.5 rounded-lg border border-hermes-border bg-hermes-elevated/50
          px-2.5 py-1.5 font-mono text-[10px] text-hermes-muted transition-all
          hover:border-hermes-cyan/40 hover:text-hermes-cyan"
      >
        <Paperclip size={11} />
      </button>
    </>
  );
}

export function AttachmentChips({
  attachments, onRemove,
}: {
  attachments: Attachment[];
  onRemove: (id: string) => void;
}) {
  if (attachments.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {attachments.map((a) => (
        <span
          key={a.id}
          className="flex items-center gap-1.5 rounded-lg border border-hermes-border bg-hermes-elevated/50
            px-2 py-1 font-mono text-[10px] text-hermes-muted"
        >
          <FileText size={10} className="text-hermes-cyan/70" />
          {a.name}
          <span className="text-hermes-dim">{Math.round(a.bytes / 1024)} Ko</span>
          <button onClick={() => onRemove(a.id)} className="text-hermes-dim hover:text-hermes-red">
            <X size={10} />
          </button>
        </span>
      ))}
    </div>
  );
}
