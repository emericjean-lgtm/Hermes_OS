"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2, ChevronLeft, CircleDot, FolderGit2, FolderOpen, GitBranch,
  GitPullRequest, ShieldAlert, Trash2, Unlink, XCircle,
} from "lucide-react";
import {
  useBindProject, useCreateProject, useCreatePullRequest, useFilesystemBrowse,
  useGitStatus, useProjects, useRemoveProject, useValidateProject,
} from "@/hooks/use-api";
import type { ProjectDTO } from "@/services/client";
import { RailPanel, Placeholder } from "./rail-primitives";

/**
 * Local folder / GitHub repo access — Workspace/Filesystem tool layer.
 *
 * A Project *is* the authorized-workspace concept the filesystem tools are
 * scoped to (backend/projects/project_manager.py's module docstring) —
 * root_path only ever grants an agent/the chat real filesystem access once
 * POST /projects/{id}/validate has really probed it on disk (see the
 * validation block below) and Aegis's dynamic whitelist picks it up
 * (security/aegis_engine.py). Folder and GitHub repo are independent
 * fields, fillable together — never one-or-the-other — mirroring Mission's
 * existing local_path/repository/branch binding (HOS-068). The directory
 * browser (GET /filesystem/browse) is read-only and lists directories
 * only; nothing about it is Aegis-gated because there is nothing yet to
 * check against before a folder is registered.
 */

const LINKED_PROJECT_KEY = "hermes.assistant.project";

function DirectoryBrowser({
  onPick, onClose,
}: {
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [browsePath, setBrowsePath] = useState<string | undefined>(undefined);
  const browse = useFilesystemBrowse(browsePath, true);

  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.14 }}
      className="absolute left-0 right-0 top-full z-30 mt-1 max-h-64 overflow-hidden rounded-lg
        border border-hermes-border-bright bg-hermes-elevated/98 shadow-panel backdrop-blur-md"
    >
      <div className="flex items-center gap-1.5 border-b border-hermes-border/60 px-2 py-1.5">
        {browse.data?.parent && (
          <button
            onClick={() => setBrowsePath(browse.data!.parent!)}
            title="Dossier parent"
            className="shrink-0 text-hermes-muted transition-colors hover:text-hermes-cyan"
          >
            <ChevronLeft size={13} />
          </button>
        )}
        <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-hermes-dim">
          {browse.data?.path ?? "Emplacements de départ"}
        </span>
        <button
          onClick={onClose}
          className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-hermes-dim
            transition-colors hover:text-hermes-red"
        >
          Fermer
        </button>
      </div>

      {browse.data?.path && (
        <button
          onClick={() => onPick(browse.data!.path!)}
          className="flex w-full items-center gap-1.5 border-b border-hermes-border/40 px-2 py-1.5
            text-left font-mono text-[10.5px] text-hermes-cyan transition-colors
            hover:bg-hermes-cyan/[0.07]"
        >
          <CheckCircle2 size={11} /> Choisir ce dossier
        </button>
      )}

      <div className="max-h-40 overflow-y-auto">
        {browse.isLoading && <Placeholder>Lecture du dossier…</Placeholder>}
        {browse.isError && (
          <Placeholder>Impossible de lire ce dossier.</Placeholder>
        )}
        {browse.data?.directories.map((name) => {
          const full = browse.data!.path ? `${browse.data!.path}\\${name}` : name;
          return (
            <button
              key={full}
              onClick={() => setBrowsePath(full)}
              className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left font-mono
                text-[10.5px] text-hermes-text transition-colors hover:bg-hermes-elevated"
            >
              <FolderOpen size={11} className="shrink-0 text-hermes-dim" /> {name}
            </button>
          );
        })}
        {browse.data && browse.data.directories.length === 0 && (
          <Placeholder>Aucun sous-dossier.</Placeholder>
        )}
      </div>
    </motion.div>
  );
}

function LinkForm({ onLinked }: { onLinked: (id: string) => void }) {
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [repository, setRepository] = useState("");
  const [branch, setBranch] = useState("");
  const [browserOpen, setBrowserOpen] = useState(false);
  const create = useCreateProject();

  const submit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!rootPath.trim() && !repository.trim()) return;
    create.mutate(
      {
        name: name.trim() || rootPath.trim() || repository.trim(),
        root_path: rootPath.trim() || undefined,
        repository: repository.trim() || undefined,
        branch: branch.trim() || undefined,
      },
      { onSuccess: (project) => onLinked(project.id) },
    );
  }, [name, rootPath, repository, branch, create, onLinked]);

  return (
    <form onSubmit={submit} className="space-y-2">
      <Placeholder>
        Donner à Hermes l&apos;accès à un dossier local et/ou un dépôt GitHub — les deux
        peuvent être renseignés ensemble.
      </Placeholder>

      <div className="relative">
        <div className="flex gap-1.5">
          <input
            value={rootPath}
            onChange={(e) => setRootPath(e.target.value)}
            placeholder="Dossier local, ex : C:\Users\...\mon-projet"
            className="min-w-0 flex-1 rounded-md border border-hermes-border bg-hermes-bg-deep/60
              px-2 py-1.5 font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim
              focus:outline-none focus:border-hermes-cyan/50"
          />
          <button
            type="button"
            onClick={() => setBrowserOpen((v) => !v)}
            title="Parcourir…"
            className="shrink-0 rounded-md border border-hermes-border px-2 text-hermes-muted
              transition-colors hover:border-hermes-cyan/40 hover:text-hermes-cyan"
          >
            <FolderOpen size={13} />
          </button>
        </div>
        <AnimatePresence>
          {browserOpen && (
            <DirectoryBrowser
              onPick={(path) => { setRootPath(path); setBrowserOpen(false); }}
              onClose={() => setBrowserOpen(false)}
            />
          )}
        </AnimatePresence>
      </div>

      <input
        value={repository}
        onChange={(e) => setRepository(e.target.value)}
        placeholder="Dépôt GitHub (optionnel), ex : owner/repo"
        className="w-full rounded-md border border-hermes-border bg-hermes-bg-deep/60 px-2 py-1.5
          font-mono text-[10.5px] text-hermes-text placeholder-hermes-dim focus:outline-none
          focus:border-hermes-cyan/50"
      />
      <input
        value={branch}
        onChange={(e) => setBranch(e.target.value)}
        placeholder="Branche (optionnel)"
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
        disabled={(!rootPath.trim() && !repository.trim()) || create.isPending}
        className="w-full rounded-md border border-hermes-cyan/40 bg-hermes-cyan/10 py-1.5
          font-mono text-[10px] uppercase tracking-wider text-hermes-cyan transition-all
          hover:bg-hermes-cyan/20 disabled:pointer-events-none disabled:opacity-40"
      >
        {create.isPending ? "Liaison…" : "Lier ce workspace"}
      </button>
      {create.isError && (
        <p className="text-[10px] text-hermes-red">
          {create.error instanceof Error ? create.error.message : "Échec de la liaison."}
        </p>
      )}
    </form>
  );
}

function ValidationBlock({ project }: { project: ProjectDTO }) {
  const validate = useValidateProject();

  if (!project.root_path) {
    return <Placeholder>Aucun dossier local — rien à valider sur disque.</Placeholder>;
  }

  if (project.validation_status !== "valid" && project.validation_status !== "invalid") {
    return (
      <button
        onClick={() => validate.mutate(project.id)}
        disabled={validate.isPending}
        className="flex w-full items-center justify-center gap-1.5 rounded-md border
          border-hermes-amber/40 bg-hermes-amber/10 py-1.5 font-mono text-[10px]
          uppercase tracking-wider text-hermes-amber transition-all hover:bg-hermes-amber/20
          disabled:pointer-events-none disabled:opacity-40"
      >
        <ShieldAlert size={11} /> {validate.isPending ? "Vérification…" : "Valider ce workspace"}
      </button>
    );
  }

  const ok = project.validation_status === "valid";
  return (
    <div className="space-y-1">
      <div className={`flex items-center gap-1.5 font-mono text-[10.5px] ${ok ? "text-hermes-green" : "text-hermes-red"}`}>
        {ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
        {ok ? "Workspace valide" : "Workspace invalide"}
      </div>
      <div className="space-y-0.5 pl-[18px] font-mono text-[9.5px] text-hermes-dim">
        <div>{project.validated_accessible ? "✓" : "✗"} Accessible</div>
        <div>{project.validated_readable ? "✓" : "✗"} Lecture</div>
        <div>{project.validated_writable ? "✓" : "✗"} Écriture</div>
        {project.validation_detail && <div className="text-hermes-dim/80">{project.validation_detail}</div>}
      </div>
      <button
        onClick={() => validate.mutate(project.id)}
        disabled={validate.isPending}
        className="mt-1 font-mono text-[9.5px] uppercase tracking-wider text-hermes-dim
          transition-colors hover:text-hermes-cyan disabled:pointer-events-none disabled:opacity-40"
      >
        {validate.isPending ? "Revérification…" : "Revalider"}
      </button>
    </div>
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

export function ProjectPanel({ sessionId }: { sessionId?: string }) {
  const [linkedId, setLinkedId] = useState<string | null>(null);
  const { data: projects } = useProjects();
  const bindProject = useBindProject();

  useEffect(() => {
    setLinkedId(typeof window !== "undefined" ? window.localStorage.getItem(LINKED_PROJECT_KEY) : null);
  }, []);

  const project = projects?.find((p) => p.id === linkedId) ?? null;
  const gitStatus = useGitStatus(project?.root_path);

  // Keep the chat's own active_project_id in sync with the panel's local
  // selection — this is what makes workspace_* tools appear for the model
  // (see backend/conversation/routes.py's _conversation_tools). Re-fires
  // whenever the linked project or the session changes.
  useEffect(() => {
    if (sessionId) bindProject.mutate({ sessionId, projectId: linkedId });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, linkedId]);

  const link = useCallback((id: string) => {
    window.localStorage.setItem(LINKED_PROJECT_KEY, id);
    setLinkedId(id);
  }, []);

  const unlink = useCallback(() => {
    window.localStorage.removeItem(LINKED_PROJECT_KEY);
    setLinkedId(null);
  }, []);

  // Delier n'agit que sur le localStorage : la fiche reste en base. Sans
  // ce bouton, un chemin mal saisi produisait un projet indelebile, et la
  // liste de selection accumulait les essais rates.
  const supprimer = useRemoveProject();
  const [aConfirmer, setAConfirmer] = useState(false);
  const oublier = useCallback(() => {
    if (!project) return;
    supprimer.mutate(project.id, {
      onSuccess: () => {
        window.localStorage.removeItem(LINKED_PROJECT_KEY);
        setLinkedId(null);
        setAConfirmer(false);
      },
    });
  }, [project, supprimer]);

  return (
    <RailPanel title="Workspace / Projet" icon={<FolderGit2 size={11} />}>
      {!project ? (
        <LinkForm onLinked={link} />
      ) : (
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate font-mono text-[11.5px] text-hermes-text-bright">{project.name}</div>
              {project.root_path && (
                <div className="truncate font-mono text-[9.5px] text-hermes-dim">{project.root_path}</div>
              )}
              {project.repository && (
                <div className="truncate font-mono text-[9.5px] text-hermes-dim">
                  {project.repository}{project.branch ? `@${project.branch}` : ""}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={unlink}
                title="Délier ce workspace de la session — la fiche est conservée"
                className="text-hermes-dim transition-colors hover:text-hermes-sodium"
              >
                <Unlink size={12} />
              </button>
              {/* Deux temps : un clic arme, le second efface. Une suppression
                  a un clic dans une colonne dense se declenche par accident,
                  et celle-ci est irreversible cote serveur. */}
              <button
                onClick={() => (aConfirmer ? oublier() : setAConfirmer(true))}
                onBlur={() => setAConfirmer(false)}
                disabled={supprimer.isPending}
                title={aConfirmer
                  ? "Confirmer : la fiche du workspace sera supprimée"
                  : "Supprimer la fiche de ce workspace (le dossier n'est pas touché)"}
                className={`transition-colors disabled:opacity-40 ${
                  aConfirmer ? "text-hermes-red" : "text-hermes-dim hover:text-hermes-red"
                }`}
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>

          {aConfirmer && (
            <p className="text-[10px] leading-relaxed text-hermes-red">
              Cliquez de nouveau pour supprimer la fiche. Le dossier sur le
              disque n&apos;est pas touché.
            </p>
          )}
          {supprimer.isError && (
            <p className="text-[10px] text-hermes-red">
              La suppression a échoué — la fiche est toujours là.
            </p>
          )}

          <ValidationBlock project={project} />

          {gitStatus.isLoading && <Placeholder>Lecture du statut git…</Placeholder>}
          {gitStatus.isError && project.root_path && (
            <Placeholder>Pas un dépôt git (ou chemin inaccessible) — workspace lié quand même.</Placeholder>
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
