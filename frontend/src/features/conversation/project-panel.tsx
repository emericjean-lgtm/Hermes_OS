"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CircleDot, FolderGit2, GitBranch, GitPullRequest, Unlink,
} from "lucide-react";
import {
  useCreateProject, useCreatePullRequest, useGitStatus, useProjects,
} from "@/hooks/use-api";
import { RailPanel, Placeholder } from "./rail-primitives";

/**
 * Local folder / GitHub repo access (Assistant v2 feedback round).
 *
 * There is no new backend here — `/api/v1/projects` (root_path) and
 * `/api/v1/git/*` (real `git` subprocess calls, `create_pull_request`
 * shelling to the actual `gh` CLI, all gated by Aegis) have existed since
 * HOS-066B and had zero Cockpit caller. "Linking a GitHub repo" is exactly
 * pointing Hermes at a local checkout whose remote happens to be GitHub —
 * there's no separate OAuth flow to fabricate.
 *
 * Only the project id is persisted client-side (localStorage), same
 * pattern as the session id: the record itself lives server-side via
 * ProjectStore.
 */

const LINKED_PROJECT_KEY = "hermes.assistant.project";

function LinkForm({ onLinked }: { onLinked: (id: string) => void }) {
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");
  const create = useCreateProject();

  const submit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!rootPath.trim()) return;
    create.mutate(
      { name: name.trim() || rootPath.trim(), root_path: rootPath.trim() },
      { onSuccess: (project) => onLinked(project.id) },
    );
  }, [name, rootPath, create, onLinked]);

  return (
    <form onSubmit={submit} className="space-y-2">
      <Placeholder>Donner à Hermes l&apos;accès à un dossier local (dépôt git ou non).</Placeholder>
      <input
        value={rootPath}
        onChange={(e) => setRootPath(e.target.value)}
        placeholder="Chemin du dossier, ex : C:\Users\...\mon-projet"
        className="w-full rounded-md border border-hermes-border bg-hermes-bg-deep/60 px-2 py-1.5
          font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim focus:outline-none
          focus:border-hermes-cyan/50"
      />
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Nom (optionnel)"
        className="w-full rounded-md border border-hermes-border bg-hermes-bg-deep/60 px-2 py-1.5
          font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim focus:outline-none
          focus:border-hermes-cyan/50"
      />
      <button
        type="submit"
        disabled={!rootPath.trim() || create.isPending}
        className="w-full rounded-md border border-hermes-cyan/40 bg-hermes-cyan/10 py-1.5
          font-mono text-[10px] uppercase tracking-wider text-hermes-cyan transition-all
          hover:bg-hermes-cyan/20 disabled:pointer-events-none disabled:opacity-40"
      >
        {create.isPending ? "Liaison…" : "Lier ce dossier"}
      </button>
      {create.isError && (
        <p className="text-[10px] text-hermes-red">
          {create.error instanceof Error ? create.error.message : "Échec de la liaison."}
        </p>
      )}
    </form>
  );
}

function PullRequestForm({ repoPath, branch }: { repoPath: string; branch: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const pr = useCreatePullRequest();

  const submit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    pr.mutate({ repo_path: repoPath, title: title.trim(), body: body.trim(), base: "main" });
  }, [title, body, repoPath, pr]);

  return (
    <div className="mt-2 border-t border-hermes-border/50 pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider
          text-hermes-muted transition-colors hover:text-hermes-cyan"
      >
        <GitPullRequest size={11} /> Créer une PR ({branch} → main)
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.form
            initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.18 }}
            onSubmit={submit}
            className="overflow-hidden"
          >
            <div className="space-y-1.5 pt-2">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Titre de la pull request"
                className="w-full rounded-md border border-hermes-border bg-hermes-bg-deep/60 px-2 py-1.5
                  font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim focus:outline-none
                  focus:border-hermes-cyan/50"
              />
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Description (optionnelle)"
                rows={2}
                className="w-full resize-none rounded-md border border-hermes-border bg-hermes-bg-deep/60
                  px-2 py-1.5 font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim
                  focus:outline-none focus:border-hermes-cyan/50"
              />
              <button
                type="submit"
                disabled={!title.trim() || pr.isPending}
                className="w-full rounded-md border border-hermes-violet/40 bg-hermes-violet/10 py-1.5
                  font-mono text-[10px] uppercase tracking-wider text-hermes-violet transition-all
                  hover:bg-hermes-violet/20 disabled:pointer-events-none disabled:opacity-40"
              >
                {pr.isPending ? "Ouverture…" : "Ouvrir la pull request"}
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* A refusal (protected branch, Aegis deny) is a normal, expected
          outcome the backend reports with applied=false — not an error to
          swallow or an exception to catch. */}
      {pr.data && (
        <div className={`mt-2 rounded-md border px-2 py-1.5 text-[10px] leading-relaxed ${
          pr.data.applied
            ? "border-hermes-green/30 bg-hermes-green/10 text-hermes-green"
            : "border-hermes-amber/30 bg-hermes-amber/10 text-hermes-amber"
        }`}
        >
          {pr.data.applied ? "PR ouverte." : `Refusée (${pr.data.verdict}) : ${pr.data.reason}`}
          {pr.data.output && <div className="mt-1 font-mono text-hermes-dim">{pr.data.output}</div>}
        </div>
      )}
      {pr.isError && (
        <p className="mt-2 text-[10px] text-hermes-red">
          {pr.error instanceof Error ? pr.error.message : "Échec de la requête."}
        </p>
      )}
    </div>
  );
}

export function ProjectPanel() {
  const [linkedId, setLinkedId] = useState<string | null>(null);
  const { data: projects } = useProjects();

  useEffect(() => {
    setLinkedId(typeof window !== "undefined" ? window.localStorage.getItem(LINKED_PROJECT_KEY) : null);
  }, []);

  const project = projects?.find((p) => p.id === linkedId) ?? null;
  const gitStatus = useGitStatus(project?.root_path);

  const link = useCallback((id: string) => {
    window.localStorage.setItem(LINKED_PROJECT_KEY, id);
    setLinkedId(id);
  }, []);

  const unlink = useCallback(() => {
    window.localStorage.removeItem(LINKED_PROJECT_KEY);
    setLinkedId(null);
  }, []);

  return (
    <RailPanel title="Projet" icon={<FolderGit2 size={11} />}>
      {!project ? (
        <LinkForm onLinked={link} />
      ) : (
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-mono text-[11.5px] text-hermes-text-bright">{project.name}</div>
              <div className="truncate font-mono text-[9.5px] text-hermes-dim">{project.root_path}</div>
            </div>
            <button
              onClick={unlink}
              title="Délier ce dossier"
              className="shrink-0 text-hermes-dim transition-colors hover:text-hermes-red"
            >
              <Unlink size={12} />
            </button>
          </div>

          {gitStatus.isLoading && <Placeholder>Lecture du statut git…</Placeholder>}
          {gitStatus.isError && (
            <Placeholder>Pas un dépôt git (ou chemin inaccessible) — dossier lié quand même.</Placeholder>
          )}
          {gitStatus.data && (
            <>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="flex items-center gap-1 rounded border border-hermes-border
                  bg-hermes-elevated/60 px-1.5 py-0.5 font-mono text-[9.5px] text-hermes-muted">
                  <GitBranch size={9} /> {gitStatus.data.branch}
                </span>
                {gitStatus.data.dirty && (
                  <span className="flex items-center gap-1 rounded border border-hermes-amber/40
                    bg-hermes-amber/10 px-1.5 py-0.5 font-mono text-[9.5px] text-hermes-amber">
                    <CircleDot size={9} /> modifié
                  </span>
                )}
                {gitStatus.data.protected && (
                  <span className="rounded border border-hermes-red/40 bg-hermes-red/10 px-1.5 py-0.5
                    font-mono text-[9.5px] text-hermes-red">protégée</span>
                )}
              </div>
              {project.root_path && !gitStatus.data.protected && (
                <PullRequestForm repoPath={project.root_path} branch={gitStatus.data.branch} />
              )}
            </>
          )}
        </div>
      )}
    </RailPanel>
  );
}
