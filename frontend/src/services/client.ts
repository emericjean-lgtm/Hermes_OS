import type {
  Mission,
  MissionGraph,
  MissionReport,
  MissionTimeline,
  Agent,
  CollaborationMessage,
  Delegation,
  RuntimeInfo,
  RuntimeDecision,
  ResourceStatus,
  MemoryEntry,
  KnowledgeGraph,
  Experience,
  SearchResult,
  Skill,
  SkillSelection,
  SkillDistribution,
  ToolDefinition,
  ToolExecution,
  ToolHealth,
  MCPServer,
  PolicyRule,
  ApprovalRequest,
  AuditEntry,
  SystemEvent,
  ExecutionSummary,
  ExecutionStatistics,
  SystemHealth,
  SystemStatistics,
  AlexandrieStatus,
  AlexandrieDocument,
  AlexandrieSearchResults,
  AlexandrieSyncHistory,
  AlexandrieSyncResult,
  AlexandrieGraphEdges,
  AlexandrieMissionDocs,
  OhMyPiStatus,
  OhMyPiCapability,
  OhMyPiExecutionResult,
  KlaatCodeStatus,
  KlaatCodeCapability,
  KlaatCodeExecutionResult,
  CodeIntelligenceStatusDTO,
  CodeIntelligenceCapabilitiesDTO,
  CodeIntelligenceProvidersDTO,
  CodeIntelligenceTaskResultDTO,
  CodeIntelligenceHistoryDTO,
} from "@/types/hermes";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

/** Pull the array out of a `{ key: [...] , total: n }` envelope.
 *
 *  Most Hermes list endpoints wrap their payload — `/agents` returns
 *  `{agents, total}`, `/tools` returns `{tools, count, stats}` and so on — but
 *  these client methods were typed as returning a bare array. Nothing caught it
 *  because the Cockpit could not reach the backend at all (the shipped
 *  `.env.local.example` omitted the `/api/v1` prefix and CORS only allowed port
 *  3000), so every call failed and the components fell back to `[]`. With
 *  connectivity restored the Dashboard crashed outright on
 *  `missions.filter is not a function`.
 *
 *  Tolerates a bare array too, so an endpoint that is already unwrapped — or is
 *  changed to be — keeps working.
 */
function unwrap<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === "object") {
    const inner = (payload as Record<string, unknown>)[key];
    if (Array.isArray(inner)) return inner as T[];
  }
  return [];
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

/** Réponse réelle de GET /api/v1/system/health (ServiceHealthProbe).
 *  Documentée ici parce qu'elle ne ressemble pas au type SystemHealth que
 *  le Cockpit manipule : statuts en minuscules, sous-systèmes sous `detail`,
 *  ni version ni uptime. La normalisation est faite ci-dessous. */
interface SubsystemHealthWire {
  status?: string;
  detail?: string;
}
interface SystemHealthWire {
  status?: string;
  services?: number;
  by_status?: Record<string, number>;
  unhealthy?: string[];
  silent?: string[];
  detail?: Record<string, SubsystemHealthWire>;
}
interface RootHealthWire {
  status?: string;
  uptime_seconds?: number;
}

const normaliseStatus = (s: string | undefined): SystemHealth["status"] => {
  const v = (s ?? "").toLowerCase();
  if (v === "healthy" || v === "ok") return "HEALTHY";
  if (v === "degraded") return "DEGRADED";
  if (v === "unhealthy" || v === "error" || v === "failed") return "UNHEALTHY";
  // "unknown" et tout statut non prévu : ne pas mentir en annonçant HEALTHY.
  return "DEGRADED";
};

// ── System ──────────────────────────────────────────
/** Voix (HOS-173).
 *
 *  Le serveur ne transcrit ni ne synthétise : le navigateur le fait sans
 *  rien coûter au GPU, et sur 16 Gio partagés avec le modèle des missions
 *  cela décide. Ce client ne porte donc que les réglages et le rapport de
 *  capacités — lequel interroge les fournisseurs plutôt que de les
 *  déclarer. */
export interface VoicePreferences {
  langue: string;
  voix: string;
  debit: number;
  hauteur: number;
  lecture_automatique: boolean;
  mains_libres: boolean;
  /** `serveur` = les modèles locaux (Piper, faster-whisper) ; `navigateur`
   *  = les API Web Speech. Le serveur est le défaut : c'est la meilleure
   *  qualité, elle est installée, et elle ne coûte rien à la VRAM — les
   *  deux modèles tournent sur CPU. */
  moteur: "serveur" | "navigateur";
}

export interface VoiceCapability {
  nom: string;
  genre: string;
  ou: string;
  disponible: boolean;
  detail: string;
}

// ── Studio (HOS-190) ─────────────────────────────────────────
/** Ce que `GET /studio/state` rend.
 *
 *  `attention_sub_quadratique` mérite d'être affiché et pas seulement
 *  vérifié : sans ce drapeau, un rendu à 16 384 jetons réclame 20,16 Gio
 *  sur une carte de 15,98 et met 3 226 ms au lieu de 187. Il aboutit —
 *  c'est bien le problème. */
export interface StudioStateDTO {
  joignable: boolean;
  version: string;
  vram_totale: number;
  vram_libre: number;
  attention_sub_quadratique: boolean;
  detail: string;
  file: { en_cours: number; en_attente: number };
}

export interface StudioModelsDTO {
  diffusion: string[];
  encodeurs: string[];
  vae: string[];
  /** Les modèles d'image sont des *checkpoints*, pas des `unet`. Sans
   *  cette liste, SDXL — installé et mesuré — n'apparaissait nulle part
   *  dans l'écran, et l'on pouvait croire qu'il n'était pas là. */
  checkpoints: string[];
}

/** Ce que le Studio Center sait composer.
 *
 *  Un gabarit est un graphe figé qu'on remplit avec des paramètres
 *  explicites : rien n'y est inféré. Le catalogue vient du backend
 *  plutôt que d'être recopié ici — deux listes du même fait finissent
 *  par diverger, et c'est celle qu'on ne regarde pas qui se trompe. */
export interface GabaritDTO {
  titre: string;
  moteur: string;
  sortie: "image" | "video";
  note: string;
  parametres: string[];
  /** Les formats que ce moteur sait rendre. SDXL s'effondre loin de ses
   *  compartiments d'entraînement, LTX déborde au-delà de 0,9 Mpx : une
   *  liste commune laissait choisir un format ruineux sans rien dire. */
  formats: string[];
}

export interface StudioGabaritsDTO {
  gabarits: Record<string, GabaritDTO>;
  formats: Record<string, { largeur: number; hauteur: number }>;
}

export interface ParametresRendu {
  format_?: string;
  images?: number;
  etapes?: number;
  graine?: number;
  cfg?: number;
  avec_son?: boolean;
}

/** `mesure: false` n'est pas « zéro octet » : c'est « le compteur n'a rien
 *  rendu ». L'écran doit écrire « non mesuré », jamais « 0 Gio ». */
export interface StudioVramDTO {
  mesure: boolean;
  pid?: number;
  octets?: number;
  raison?: string;
}

/** Un plan de la file de nuit, tel que le journal le consigne.
 *
 *  `etat` porte sept valeurs et non deux, parce que « terminé » et
 *  « réussi » ne sont pas la même chose ici. Un plan `indetermine` a bien
 *  produit un fichier : c'est la relecture qui n'a pas pu se faire. Le
 *  compter comme retenu serait le `success: true` au-dessus d'un
 *  workspace vide que ce dépôt a déjà payé cinq fois. */
export type EtatPlanNuit =
  | "en_attente" | "rendu" | "retenu" | "rejete"
  | "indetermine" | "echoue" | "abandonne";

export interface PlanNuitDTO {
  identifiant: string;
  consigne: string;
  etat: EtatPlanNuit;
  fichiers: string[];
  duree_s: number;
  pic_vram_octets: number;
  confiance: number;
  defauts: string[];
  raison: string;
}

export interface RapportNuitDTO {
  debut: number;
  fin: number;
  duree_s: number;
  arret_anticipe: string;
  compte: Record<string, number>;
  plans: PlanNuitDTO[];
}

export const studioClient = {
  state: () => fetchJSON<StudioStateDTO>("/studio/state"),
  night: () => fetchJSON<{
    en_cours: boolean; rapport: RapportNuitDTO | null; raison?: string;
  }>("/studio/night"),
  models: () => fetchJSON<StudioModelsDTO>("/studio/models"),
  vram: () => fetchJSON<StudioVramDTO>("/studio/vram"),
  queue: () => fetchJSON<{ joignable: boolean; en_cours: number; en_attente: number }>(
    "/studio/queue"),
  render: (graphe: Record<string, unknown>, besoin_octets?: number) =>
    fetchJSON<{
      success: boolean; prompt_id?: string; error?: string; raison?: string;
      modeles_decharges?: string[]; vram_liberee_octets?: number;
    }>("/studio/render", {
      method: "POST",
      body: JSON.stringify({ graphe, ...(besoin_octets ? { besoin_octets } : {}) }),
    }),
  templates: () => fetchJSON<StudioGabaritsDTO>("/studio/templates"),
  /** Composer et soumettre en un appel. Rend la main dès la soumission :
   *  un plan dure des minutes et aucune requête HTTP ne doit les
   *  attendre. Le suivi passe par `/studio/queue`. */
  composer: (gabarit: string, consigne: string, parametres: ParametresRendu) =>
    fetchJSON<{
      success: boolean; prompt_id?: string; error?: string; raison?: string;
      modeles_decharges?: string[]; vram_liberee_octets?: number;
    }>("/studio/render", {
      method: "POST",
      body: JSON.stringify({ gabarit, consigne, parametres }),
    }),
};

export const voiceClient = {
  /** POST /voice/speak — un WAV synthétisé par la voix locale.
   *
   *  Rend un `Blob` et non du JSON : `fetchJSON` ne convient pas ici, la
   *  réponse est de l'audio. Lève si le serveur n'a pas de voix locale,
   *  pour que l'appelant puisse retomber sur le navigateur au lieu de
   *  rester muet. */
  speak: async (texte: string, voix?: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texte, ...(voix ? { voix } : {}) }),
    });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.blob();
  },

  /** POST /voice/transcribe — le texte d'un audio téléversé.
   *
   *  `multipart/form-data` sans en-tête explicite : le navigateur doit
   *  poser lui-même la frontière du multipart, et la fixer à la main
   *  produit un corps que le serveur ne sait pas relire. */
  transcribe: async (audio: Blob, nom = "dictee.webm"): Promise<{ texte: string; fournisseur: string }> => {
    const corps = new FormData();
    corps.append("fichier", audio, nom);
    const res = await fetch(`${API_BASE}/voice/transcribe`, { method: "POST", body: corps });
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  },

  state: () =>
    fetchJSON<{ preferences: VoicePreferences; capacites: VoiceCapability[] }>(
      "/voice/state",
    ),
  savePreferences: (p: VoicePreferences) =>
    fetchJSON<{ preferences: VoicePreferences }>("/voice/preferences", {
      method: "PUT",
      body: JSON.stringify(p),
    }),
};

export const systemClient = {
  /** Le Cockpit interrogeait GET /health, qui est la sonde de vivacité
   *  héritée : elle renvoie `{"status": "ok", "uptime_seconds": …}` et rien
   *  d'autre. Le bandeau affichait donc « UNKNOWN » en permanence (le
   *  Cockpit compare à "HEALTHY") et n'avait aucun sous-système à lister.
   *  La vraie sonde agrégée est /system/health (34 services). Les deux sont
   *  interrogées : l'une pour le détail par sous-système, l'autre parce
   *  qu'elle seule expose l'uptime du processus. */
  health: async (): Promise<SystemHealth> => {
    const [agg, root] = await Promise.all([
      fetchJSON<SystemHealthWire>("/system/health"),
      fetchJSON<RootHealthWire>("/health").catch(() => ({} as RootHealthWire)),
    ]);
    // The wire payload's own `silent` array already distinguishes "no
    // telemetry accessor exists for this subsystem" from "reporting a real
    // problem" — both used to collapse into the same DEGRADED status here,
    // which made an architectural gap (12 of 35 subsystems, confirmed real)
    // read as 12 incidents. Read the real list rather than re-deriving it.
    const silent = new Set(agg.silent ?? []);
    const subsystems: SystemHealth["subsystems"] = {};
    for (const [name, info] of Object.entries(agg.detail ?? {})) {
      subsystems[name] = {
        status: silent.has(name) ? "NOT_INSTRUMENTED" : normaliseStatus(info?.status),
        message: info?.detail,
      };
    }
    return {
      status: normaliseStatus(agg.status),
      version: "",
      uptime_seconds: root.uptime_seconds ?? 0,
      subsystems,
    };
  },
  /** /system/statistics renvoie `{services: {<clé>: {…}}}`, pas les champs
   *  plats (`missions_total`, `agents_active`…) que le type SystemStatistics
   *  déclare. Toutes ces lectures valaient donc `undefined`, et la barre
   *  d'état affichait « 0/0 » partout en permanence. On projette ici la
   *  charge utile réelle sur le type attendu ; `raw` reste exposé pour les
   *  Centers qui ont besoin du détail par service. */
  statistics: async (): Promise<SystemStatistics> => {
    const raw = await fetchJSON<Record<string, any>>("/system/statistics");
    const svc = (raw?.services ?? {}) as Record<string, any>;
    const sched = svc.execution_engine?.scheduler ?? {};
    const coord = svc.execution_engine?.coordinator ?? {};
    const sup = svc.agent_supervisor ?? {};
    const mem = svc.memory_manager ?? {};
    const num = (v: unknown) => (typeof v === "number" ? v : 0);

    return {
      missions_total: num(sched.total),
      missions_active: num(sched.running) + num(sched.pending),
      missions_completed: num(sched.completed),
      missions_failed: num(sched.failed),
      agents_total: num(sup.total_agents) || num(coord.agents_registered),
      agents_active: num(sup.busy),
      runtimes_total: num(svc.runtime_orchestrator?.known_runtimes),
      runtimes_healthy: num(coord.runtimes_available),
      memory_entries:
        num(mem.episodic?.total) +
        num(mem.semantic?.total) +
        num(mem.procedural?.total_procedures),
      raw,
    } as SystemStatistics;
  },
  // GET /version n'existe pas (404) : méthode retirée (P-002 §7).
  /** HOS-075 — le rôle → modèle réel de config/models.yaml, croisé avec ce
   *  qu'Ollama tient réellement chargé. Alimente le sélecteur de modèle
   *  manuel de l'Assistant : chaque rôle proposé est un vrai modèle avec
   *  un vrai num_ctx, pas une liste inventée côté frontend. */
  models: () => fetchJSON<{ roles: SystemModelRoleDTO[]; loaded_count: number; roles_sans_modele: string[] }>("/system/models"),
  /** HOS-141 — le harnais sert-il vraiment, ou est-on retombé sur un agent
   *  jeté après chaque tâche ? Les deux modes produisent des résultats de
   *  **même forme** : sans cette route, la dégradation est invisible. */
  harnais: () => fetchJSON<HarnaisDTO>("/system/harnais"),
};

export interface HarnaisDTO {
  actif: boolean;
  pret: boolean;
  explication: string;
  prerequis: { agent_installe: boolean; backend_joignable: boolean; mcp_declare: boolean };
  sessions_ouvertes: number;
}

export interface SystemModelRoleDTO {
  role: string;
  model: string;
  tier: string;
  vram_gb: number | null;
  always_loaded: boolean;
  /** Résident en VRAM. Sur cette machine un seul modèle l'est à la fois :
   *  `false` est donc le cas **normal**, pas une anomalie. */
  loaded: boolean;
  /** Présent sur le disque. `null` quand Ollama est injoignable — « on ne
   *  sait pas » n'est pas « absent » (HOS-139). */
  installe: boolean | null;
  description: string;
}

// ── Missions ─────────────────────────────────────────
/** GET /api/v1/missions returns `mission_id` and a bare `progress` number
 *  (0-100); GET /api/v1/missions/{id} returns the same `mission_id` but a
 *  `progress` *object* (`{total, completed, progress_pct, ...}` — see
 *  backend/mission/dependency_resolver.py) plus `description`/`created_at`,
 *  which the list endpoint omits entirely. Every mission therefore had
 *  `id === undefined` (MissionCenter read `.id`, never `.mission_id`) —
 *  every row shared the same React key, and `.find(m => m.id === selected)`
 *  always matched the first mission regardless of which one was clicked.
 *  This normalises both shapes onto the one `Mission` type. */
function toMission(raw: Record<string, any>): Mission {
  const progress = raw.progress;
  const progressIsDetail = progress && typeof progress === "object";
  return {
    ...raw,
    id: raw.id ?? raw.mission_id,
    progress: progressIsDetail ? progress.progress_pct ?? 0 : progress ?? 0,
    node_count: progressIsDetail ? progress.total : raw.nodes,
    completed_nodes: progressIsDetail ? progress.completed : undefined,
    // MissionStatus (types/hermes.ts) is declared uppercase; the backend's
    // MissionStatus enum values are lowercase ("running", "validated", ...).
    // Without this, every status-keyed lookup (statusBadge, disabled-state
    // checks) silently missed on every mission.
    status: String(raw.status ?? "").toUpperCase(),
  } as Mission;
}

export const missionsClient = {
  list: () =>
    fetchJSON<unknown>("/missions")
      .then((d) => unwrap<Record<string, any>>(d, "missions"))
      .then((rows) => rows.map(toMission)),
  get: (id: string) => fetchJSON<Record<string, any>>(`/missions/${id}`).then(toMission),
  create: (data: Partial<Mission>) =>
    fetchJSON<Mission>("/missions", { method: "POST", body: JSON.stringify(data) }),
  graph: (id: string) => fetchJSON<MissionGraph>(`/missions/${id}/graph`),
  progress: (id: string) => fetchJSON<{ progress: number; completed: number; total: number }>(
    `/missions/${id}/progress`
  ),
  start: (id: string) => fetchJSON<Mission>(`/missions/${id}/start`, { method: "POST" }),
  pause: (id: string) => fetchJSON<Mission>(`/missions/${id}/pause`, { method: "POST" }),
  resume: (id: string) => fetchJSON<Mission>(`/missions/${id}/resume`, { method: "POST" }),
  cancel: (id: string) => fetchJSON<Mission>(`/missions/${id}/cancel`, { method: "POST" }),
  report: (id: string) => fetchJSON<MissionReport>(`/missions/${id}/report`),
};

// ── Agents ───────────────────────────────────────────
/** GET /api/v1/agents renvoie `agent_id`, `preferred_runtime` et
 *  `preferred_model` — pas `id`, `type` ni `runtime`. Chaque agent avait donc
 *  `id === undefined`, ce qui donnait dix clés React identiques (« Each child
 *  in a list should have a unique key ») et un `type` vide sous chaque nom
 *  dans le Dashboard. On projette ici la charge utile réelle sur le type
 *  Agent, en gardant les champs d'origine. */
function toAgent(raw: Record<string, any>): Agent {
  return {
    ...raw,
    id: raw.id ?? raw.agent_id ?? raw.name,
    name: raw.name ?? raw.agent_id ?? "(inconnu)",
    type: raw.type ?? raw.preferred_model ?? "",
    runtime: raw.runtime ?? raw.preferred_runtime ?? "",
    capabilities: Array.isArray(raw.capabilities) ? raw.capabilities : [],
    // AgentStatus (types/hermes.ts) is declared uppercase; the backend's
    // AgentStatus enum values are lowercase ("ready", "busy", ...). Without
    // this, every status-keyed lookup (statusBadge, dashboard counts,
    // disabled-state checks) silently missed for every agent.
    status: String(raw.status ?? "").toUpperCase(),
  } as Agent;
}

export const agentsClient = {
  list: () =>
    fetchJSON<unknown>("/agents")
      .then((d) => unwrap<Record<string, any>>(d, "agents"))
      .then((rows) => rows.map(toAgent)),
  get: (id: string) => fetchJSON<Record<string, any>>(`/agents/${id}`).then(toAgent),
  create: (data: Partial<Agent>) =>
    fetchJSON<Agent>("/agents", { method: "POST", body: JSON.stringify(data) }),
  start: (id: string) => fetchJSON<Agent>(`/agents/${id}/start`, { method: "POST" }),
  stop: (id: string) => fetchJSON<Agent>(`/agents/${id}/stop`, { method: "POST" }),
  pause: (id: string) => fetchJSON<Agent>(`/agents/${id}/pause`, { method: "POST" }),
  metrics: () => fetchJSON<Record<string, number>>("/agents/metrics"),
};

// ── Collaboration ────────────────────────────────────
export const collaborationClient = {
  messages: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    // {messages, total} envelope. Typed as a bare array, this crashed the Agent
    // Center on `messages.slice is not a function` — and because the crash
    // escaped the Center, it took the whole Cockpit shell down with it (R-004).
    return fetchJSON<unknown>(`/collaboration/messages${qs}`)
      .then((d) => unwrap<CollaborationMessage>(d, "messages"));
  },
  sendMessage: (data: Partial<CollaborationMessage>) =>
    fetchJSON<CollaborationMessage>("/collaboration/messages", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  delegate: (data: Partial<Delegation>) =>
    fetchJSON<Delegation>("/collaboration/delegate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  review: (data: { task_id: string; reviewer_agent: string }) =>
    fetchJSON<{ status: string }>("/collaboration/review", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  history: (mission_id?: string) => {
    const qs = mission_id ? "?mission_id=" + mission_id : "";
    return fetchJSON<unknown>(`/collaboration/history${qs}`)
      .then((d) => unwrap<CollaborationMessage>(d, "messages"));
  },
};

// ── Runtime ──────────────────────────────────────────
export const runtimeClient = {
  list: () => fetchJSON<unknown>("/runtimes").then((d) => unwrap<RuntimeInfo>(d, "runtimes")),
  get: (name: string) => fetchJSON<RuntimeInfo>(`/runtimes/${name}`),
  health: () => fetchJSON<Record<string, { status: string; latency_ms: number }>>("/runtimes/health"),
  metrics: () => fetchJSON<Record<string, unknown>>("/runtimes/metrics"),
  // `/runtime/resources/status` n'existe pas (404) : la route est
  // `/runtime/resources`. Le Runtime Center n'a donc jamais affiché la
  // moindre jauge de ressources — la requête échouait à chaque fois et le
  // garde `resources && …` masquait l'erreur en n'affichant rien.
  resources: () => fetchJSON<ResourceStatus>("/runtime/resources"),
  allocations: () => fetchJSON<Record<string, unknown>[]>("/runtime/resources/allocations"),
  release: (data: { resource_id: string }) =>
    fetchJSON<{ status: string }>("/runtime/resources/release", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // POST /runtime/select n'existe pas côté backend (404). La méthode a été
  // retirée plutôt que laissée à pointer dans le vide (P-002 §7).
  // HOS-072: modèle(s) réellement chargés dans Ollama (/api/ps), et action
  // réelle pour en décharger un immédiatement — contrairement à
  // `allocations`/`release` ci-dessus, jamais alimentés par le vrai chemin
  // d'exécution (voir le docstring du module backend).
  loadedModels: () =>
    fetchJSON<{ success: boolean; models: LoadedModelDTO[] }>("/runtime/resources/loaded-models"),
  unloadModel: (model: string) =>
    fetchJSON<{ success: boolean; model?: string; error?: string }>("/runtime/resources/unload", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
};

export interface LoadedModelDTO {
  name: string;
  size_bytes: number;
  size_vram_bytes: number;
  expires_at: string | null;
}

// ── Memory ───────────────────────────────────────────
export const memoryClient = {
  search: (q: string, mode: "hybrid" | "graph" | "keyword" = "hybrid") =>
    fetchJSON<SearchResult[]>(`/memory/search?q=${encodeURIComponent(q)}&mode=${mode}`),
  searchAdvanced: (data: Record<string, unknown>) =>
    fetchJSON<unknown>("/memory/search", {
      method: "POST",
      body: JSON.stringify(data),
    }).then((d) => unwrap<SearchResult>(d, "results")),
  graph: (node_id?: string, depth?: number) => {
    const qs = new URLSearchParams();
    if (node_id) qs.set("node_id", node_id);
    if (depth) qs.set("depth", String(depth));
    return fetchJSON<KnowledgeGraph>(`/memory/graph?${qs}`);
  },
  experiences: () => fetchJSON<unknown>("/memory/experiences").then((d) => unwrap<Experience>(d, "recommendations")),
  index: (data: Record<string, unknown>) =>
    fetchJSON<MemoryEntry>("/memory/index", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  statistics: () => fetchJSON<Record<string, number>>("/memory/statistics"),
};

// ── Skills ───────────────────────────────────────────
/** Les competences que Hermes Agent porte reellement (HOS-176).
 *
 *  Distinct de `skillsClient.list()`, qui sert le registre du
 *  `SkillDistributor` — vide, mesure a `count: 0`. Les fondre ferait croire
 *  le distributeur peuple. */
export interface AgentSkills {
  total: number;
  racine: string;
  domaines: {
    nom: string;
    competences: { nom: string; description: string }[];
  }[];
}

export const skillsClient = {
  list: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    // {skills, count, stats} envelope — the last of the query-string list
    // methods that a literal-path contract check could not reach (R-004).
    return fetchJSON<unknown>(`/skills${qs}`).then((d) => unwrap<Skill>(d, "skills"));
  },
  get: (id: string) => fetchJSON<Skill>(`/skills/${id}`),
  agentSkills: () => fetchJSON<AgentSkills>("/skills/agent"),
  select: (data: { task_description: string; domain?: string }) =>
    fetchJSON<unknown>("/skills/select", {
      method: "POST",
      body: JSON.stringify(data),
    }).then((d) => unwrap<SkillSelection>(d, "selections")),
  load: (data: { skill_id: string; agent_id: string }) =>
    fetchJSON<Skill>("/skills/load", { method: "POST", body: JSON.stringify(data) }),
  unload: (data: { skill_id: string; agent_id: string }) =>
    fetchJSON<{ status: string }>("/skills/unload", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cache: () => fetchJSON<Record<string, unknown>>("/skills/cache"),
  statistics: () => fetchJSON<Record<string, number>>("/skills/statistics"),
};

// ── Tools ────────────────────────────────────────────
export interface ToolHealthSummary {
  total: number;
  healthy: number;
  degraded_or_unhealthy: number;
  avg_latency_ms: number;
}

/** Ce que `GET /tools/agent` rend : les outils que Hermes Agent peut
 *  reellement appeler, groupes par famille.
 *
 *  A distinguer de `ToolDefinition`, qui decrit une entree du registre
 *  declare — celui dont aucune entree n'a d'executeur. */
export interface AgentToolFamilyDTO {
  nom: string;
  total: number;
  outils: { nom: string; resume: string }[];
}

export interface AgentToolsDTO {
  success: boolean;
  total: number;
  familles: AgentToolFamilyDTO[];
}

export const toolsClient = {
  /** GET /tools/agent — la surface d'execution reelle (HOS-187). */
  agent: () => fetchJSON<AgentToolsDTO>("/tools/agent"),
  list: () => fetchJSON<unknown>("/tools").then((d) => unwrap<ToolDefinition>(d, "tools")),
  get: (id: string) => fetchJSON<ToolDefinition>(`/tools/${id}`),
  register: (data: Partial<ToolDefinition>) =>
    fetchJSON<ToolDefinition>("/tools/register", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  execute: (data: { tool_id: string; params: Record<string, unknown>; agent_id?: string }) =>
    fetchJSON<ToolExecution>("/tools/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  select: (data: { task: Record<string, unknown>; agent_id?: string }) =>
    fetchJSON<{ tool_id: string; score: number; justification: string }>("/tools/select", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  // An aggregate, not a per-tool list: the endpoint returns
  // {total, healthy, degraded_or_unhealthy, avg_latency_ms}. Typing it as
  // ToolHealth[] made tools-center call .map() on an object (R-003).
  health: () => fetchJSON<ToolHealthSummary>("/tools/health"),
  metrics: () => fetchJSON<Record<string, number>>("/tools/metrics"),
  mcpServers: () => fetchJSON<unknown>("/mcp/servers").then((d) => unwrap<MCPServer>(d, "servers")),
  mcpConnect: (data: { server_name: string; transport: string; endpoint: string }) =>
    fetchJSON<MCPServer>("/mcp/connect", { method: "POST", body: JSON.stringify(data) }),
  mcpDisconnect: (data: { server_name: string }) =>
    fetchJSON<{ status: string }>("/mcp/disconnect", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Governance ───────────────────────────────────────
export const governanceClient = {
  rules: () => fetchJSON<unknown>("/policy/rules").then((d) => unwrap<PolicyRule>(d, "rules")),
  evaluate: (data: { operation: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<{ verdict: string; reason: string; rule_id?: string }>("/policy/evaluate", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  approvals: () => fetchJSON<unknown>("/approval").then((d) => unwrap<ApprovalRequest>(d, "approvals")),
  approve: (id: string, comment?: string) =>
    fetchJSON<ApprovalRequest>(`/approval/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),
  reject: (id: string, comment?: string) =>
    fetchJSON<ApprovalRequest>(`/approval/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ comment }),
    }),
  audit: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    // {entries, total} envelope. Typed as a bare array, `auditLog.slice(0, 30)`
    // in the Governance Center threw and took the whole shell down (R-004).
    return fetchJSON<unknown>(`/audit${qs}`)
      .then((d) => unwrap<AuditEntry>(d, "entries"));
  },
};

// ── Execution ────────────────────────────────────────
// One row per real task execution (a mission node, driven through
// ExecutionController since HOS-069 — see execution_controller.py), not
// per mission. /execution/start (below) registers tasks directly against
// the standalone controller but nothing in the Cockpit currently calls it;
// real activity arrives here via Missions/Autonomous instead.
export const executionClient = {
  start: (data: { goal: string; tasks: unknown[]; mission_id?: string; priority?: string }) =>
    fetchJSON<{ execution_id: string; state: string; tasks_registered: number; user_goal: string }>(
      "/execution/start",
      { method: "POST", body: JSON.stringify(data) },
    ),
  get: (id: string) => fetchJSON<ExecutionSummary>(`/execution/${id}`),
  list: () => fetchJSON<ExecutionSummary[]>("/execution"),
  pause: (id: string) =>
    fetchJSON<{ execution_id: string; paused: boolean }>(`/execution/${id}/pause`, { method: "POST" }),
  resume: (id: string) =>
    fetchJSON<{ execution_id: string; resumed: boolean }>(`/execution/${id}/resume`, { method: "POST" }),
  cancel: (id: string) =>
    fetchJSON<{ execution_id: string; cancelled: boolean }>(`/execution/${id}/cancel`, { method: "POST" }),
  timeline: (id: string) => fetchJSON<MissionTimeline>(`/execution/${id}/timeline`),
  statistics: () => fetchJSON<ExecutionStatistics>("/execution/statistics"),
};

// ── Events ───────────────────────────────────────────
export const eventsClient = {
  list: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params) : "";
    // /api/v1/events does not exist — it 404s. The event log lives at
    // /api/v1/runtime/events and answers {events, total, runtime_id} (R-004).
    return fetchJSON<unknown>(`/runtime/events${qs}`)
      .then((d) => unwrap<SystemEvent>(d, "events"));
  },
};

// ── Alexandrie ───────────────────────────────────────
export const alexandrieClient = {
  health: () => fetchJSON<{ healthy: boolean; error?: string }>("/alexandrie/health"),
  status: () => fetchJSON<AlexandrieStatus>("/alexandrie/status"),
  documents: () =>
    fetchJSON<{ total: number; documents: AlexandrieDocument[] }>("/alexandrie/documents"),
  getDocument: (id: string) => fetchJSON<AlexandrieDocument>(`/alexandrie/documents/${id}`),
  createDocument: (data: { title: string; content: string; user_id?: string; is_public?: boolean }) =>
    fetchJSON<AlexandrieDocument>("/alexandrie/documents", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteDocument: (id: string) =>
    fetchJSON<{ status: string }>(`/alexandrie/documents/${id}`, { method: "DELETE" }),
  search: (q: string, mode: "hybrid" | "fulltext" | "semantic" = "hybrid", limit = 20) =>
    fetchJSON<AlexandrieSearchResults>(
      `/alexandrie/search?q=${encodeURIComponent(q)}&mode=${mode}&limit=${limit}`
    ),
  sync: (data: { user_id?: string; incremental?: boolean }) =>
    fetchJSON<AlexandrieSyncResult>("/alexandrie/sync", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  syncStatus: () =>
    fetchJSON<{ last_sync_at: string | null; documents_synced: number }>("/alexandrie/sync/status"),
  syncHistory: (limit = 50) =>
    fetchJSON<AlexandrieSyncHistory>(`/alexandrie/sync/history?limit=${limit}`),
  graph: (node_id?: string) => {
    const qs = node_id ? `?node_id=${node_id}` : "";
    return fetchJSON<AlexandrieGraphEdges>(`/alexandrie/graph${qs}`);
  },
  cacheStats: () =>
    fetchJSON<{ entries: number; hits: number; misses: number; hit_rate: number }>(
      "/alexandrie/cache/stats"
    ),
  cachePrune: () =>
    fetchJSON<{ removed: number }>("/alexandrie/cache/prune", { method: "POST" }),
  linkToMission: (data: { document_id: string; mission_id: string }) =>
    fetchJSON<{ linked: boolean }>("/alexandrie/missions/link", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  missionDocuments: (mission_id: string) =>
    fetchJSON<AlexandrieMissionDocs>(`/alexandrie/missions/${mission_id}/documents`),
  relevantDocuments: (data: { tags: string[]; limit?: number }) =>
    fetchJSON<{ documents: { id: string; title: string; relevance: number }[] }>(
      "/alexandrie/missions/relevant",
      { method: "POST", body: JSON.stringify(data) }
    ),
  events: (limit = 50) =>
    fetchJSON<{ total: number; events: Record<string, unknown>[] }>(
      `/alexandrie/events?limit=${limit}`
    ),
};

// ── Oh My Pi ──────────────────────────────────────────
export const ohmypiClient = {
  // The endpoint wraps the payload in a "status" envelope, exactly like
  // /klaatcode/status does. This was typed as the bare inner object, so
  // every field read off it was undefined at runtime (R-002 P3).
  status: () => fetchJSON<{ status: OhMyPiStatus }>("/ohmypi/status"),
  capabilities: () =>
    fetchJSON<{ capabilities: OhMyPiCapability[]; count: number }>(
      "/ohmypi/capabilities"
    ),
  execute: (data: {
    action: string;
    parameters?: Record<string, unknown>;
    agent_id?: string;
    mission_id?: string;
  }) =>
    fetchJSON<OhMyPiExecutionResult>("/ohmypi/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── KlaatCode ─────────────────────────────────────────
export const klaatcodeClient = {
  status: () => fetchJSON<KlaatCodeStatus>("/klaatcode/status"),
  capabilities: () =>
    fetchJSON<{ capabilities: KlaatCodeCapability[]; count: number }>(
      "/klaatcode/capabilities"
    ),
  analyze: (data: { path: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/analyze", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  execute: (data: {
    action: string;
    parameters?: Record<string, unknown>;
    agent_id?: string;
    mission_id?: string;
  }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/execute", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  diagnostics: (data: { file: string; agent_id?: string; mission_id?: string }) =>
    fetchJSON<KlaatCodeExecutionResult>("/klaatcode/diagnostics", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Code Intelligence (R-006) ─────────────────────────
export type CodeIntelligenceTaskKind = "analyze" | "review" | "debug" | "explain";

export interface CodeIntelligenceTaskRequest {
  project_path?: string;
  language?: string;
  parameters?: Record<string, unknown>;
  mission_id?: string;
  node_id?: string;
  /** "klaatcode" | "ohmypi" | "hermes_native" | "hybrid" — omit for Auto. */
  force_provider?: string;
}

export const codeIntelligenceClient = {
  status: () => fetchJSON<CodeIntelligenceStatusDTO>("/code-intelligence/status"),
  capabilities: () =>
    fetchJSON<CodeIntelligenceCapabilitiesDTO>("/code-intelligence/capabilities"),
  providers: () => fetchJSON<CodeIntelligenceProvidersDTO>("/code-intelligence/providers"),
  history: (limit = 50) =>
    fetchJSON<CodeIntelligenceHistoryDTO>(`/code-intelligence/history?limit=${limit}`),
  runTask: (kind: CodeIntelligenceTaskKind, body: CodeIntelligenceTaskRequest) =>
    fetchJSON<CodeIntelligenceTaskResultDTO>(`/code-intelligence/${kind}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ── Evolution (R-001: real endpoints, no client-side mocks) ─────────
//
// The Evolution Center used to render module-level MOCK_PROPOSALS /
// MOCK_REPORTS constants, so its counters were fabricated in the browser no
// matter what the backend said. These call the real /api/v1/evolution routes.

export interface EvolutionProposalDTO {
  proposal_id: string;
  evolution_type: string;
  target_component: string;
  description: string;
  expected_gain: number;
  risk_level: string;
  confidence: number;
  status: string;
}

export interface EvolutionReportDTO {
  report_id: string;
  improvements_found: number;
  applied_changes: string[];
  rejected_changes: string[];
  total_gain_percent: number;
}

export const evolutionClient = {
  status: () => fetchJSON<Record<string, unknown>>("/evolution/status"),
  proposals: (status?: string) =>
    fetchJSON<EvolutionProposalDTO[]>(
      status ? `/evolution/proposals?status=${encodeURIComponent(status)}` : "/evolution/proposals",
    ),
  reports: (limit = 10) => fetchJSON<EvolutionReportDTO[]>(`/evolution/reports?limit=${limit}`),
  approve: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/approve/${id}`, { method: "POST" }),
  apply: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/apply/${id}`, { method: "POST" }),
  // POST /evolution/simulate/{id} existe côté backend et n'avait aucun appelant.
  simulate: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/evolution/simulate/${id}`, { method: "POST" }),
  analyze: () =>
    fetchJSON<Record<string, unknown>>("/evolution/analyze", { method: "POST" }),
};

// ── Security & System (RC3: these Centers had no data source at all) ──
//
// security-center.tsx imported only useState and rendered MOCK_STATUS /
// MOCK_TRUST_SCORES — 42 permissions, trust scores of 94.2/88.5/82.1 — all
// invented in the browser while /api/v1/security/status returned real values.
// system-center.tsx was the same.

export interface SecurityStatusDTO {
  permissions: { total_permissions: number; total_policies: number; history_entries?: number };
  trust: {
    total_agents: number;
    average_score: number;
    by_level: Record<string, number>;
    total_violations?: number;
    total_approvals?: number;
  };
  threats?: Record<string, unknown>;
  isolation?: Record<string, unknown>;
}

/** Le curseur d'autonomie (§17.5) et ce que chaque cran change réellement.
 *
 * `always_validated` liste les catégories qu'aucun niveau ne débloque
 * (§17.3). Elle vient du backend et non d'une constante ici : la
 * conséquence d'un réglage de sécurité appartient au module qui l'applique,
 * pas à celui qui le dessine — sans quoi l'interface finirait par promettre
 * une permissivité que le moteur refuse. */
export interface AutonomyDTO {
  level: string;
  levels: { name: string; effect: string }[];
  overridden: boolean;
  always_validated: string[];
}

export const securityClient = {
  status: () => fetchJSON<SecurityStatusDTO>("/security/status"),
  autonomy: () => fetchJSON<AutonomyDTO>("/security/autonomy"),
  setAutonomy: (level: string) =>
    fetchJSON<AutonomyDTO>("/security/autonomy", {
      method: "PUT",
      body: JSON.stringify({ level }),
    }),
  resetAutonomy: () =>
    fetchJSON<AutonomyDTO>("/security/autonomy", { method: "DELETE" }),
  policies: () => fetchJSON<Record<string, unknown>[]>("/security/policies"),
  threats: (limit = 50) => fetchJSON<Record<string, unknown>[]>(`/security/threats?limit=${limit}`),
  events: (limit = 100) => fetchJSON<Record<string, unknown>[]>(`/security/events?limit=${limit}`),
  trust: (agentId: string) => fetchJSON<Record<string, unknown>>(`/security/trust/${agentId}`),
};

export interface SubsystemHealthDTO {
  status: string;
  services: number;
  by_status: Record<string, number>;
  unhealthy: string[];
  silent: string[];
  detail: Record<string, { status: string; detail?: string }>;
}

export const subsystemClient = {
  health: () => fetchJSON<SubsystemHealthDTO>("/system/health"),
  ready: () => fetchJSON<Record<string, unknown>>("/system/ready"),
  statistics: () => fetchJSON<Record<string, unknown>>("/system/statistics"),
  assembly: () => fetchJSON<Record<string, unknown>>("/system/assembly"),
  dependencies: () => fetchJSON<Record<string, unknown>>("/system/dependencies"),
};

// ── Autonomous (HOS-063) ──────────────────────────────────
// The Autonomous Center rendered module-level MOCK_GOAL / MOCK_SESSION /
// MOCK_DECISIONS / MOCK_TIMELINE constants — a fabricated goal, a fabricated
// session on a "ktransformers" runtime and four invented decisions — while this
// API was fully working and doing real inference. There was no client at all
// for the most capable surface Hermes has (R-002 P3).

export interface AutonomousGoalDTO {
  goal_id: string;
  user_request: string;
  interpreted_goal: string;
  status: string;
  domain: string;
  language: string;
  complexity: number;
  priority: string;
  estimated_duration_s: number;
  // Project binding (HOS-067) — empty strings when the goal isn't bound to
  // a specific local checkout or GitHub repository.
  local_path: string;
  repository: string;
  branch: string;
  // Real prior-experience summary gathered before planning (HOS-067) —
  // empty on a fresh deployment with no mission history yet.
  knowledge_context: string;
  created_at: string;
  /** La mission DAG que cet objectif exécute réellement (HOS-117).
   *
   * Ajouté par `GET /autonomous/{id}` depuis la session, seule à porter ce
   * lien. Chaîne vide quand la planification n'a pas encore produit de
   * mission — jamais absent, pour qu'un appelant n'ait pas à distinguer
   * « pas de mission » de « ancienne version du backend ».
   *
   * Présent uniquement sur `GET /autonomous/{id}` : la liste
   * `/autonomous/goals` ne l'enrichit pas. */
  mission_id?: string;
}

export interface AutonomousDecisionDTO {
  decision_id: string;
  decision_type: string;
  reason: string;
  confidence: number;
  alternatives_count: number;
  selected: string;
  context: Record<string, unknown>;
  timestamp: string;
}

export interface AutonomousReportDTO {
  goal_id: string;
  user_request: string;
  interpreted_goal: string;
  execution_summary: string;
  results: Record<string, unknown>;
  improvements: string[];
  lessons: string[];
  decisions: AutonomousDecisionDTO[];
  total_duration_ms: number;
  agents_used: string[];
  runtimes_used: string[];
  tools_used: string[];
  success: boolean;
  /**
   * Ce que le disque et les tests du livrable disent, à côté de ce que la
   * mission prétend (HOS-121). `success` seul a déjà menti : sur l'essai
   * Skills360 il valait `true` au-dessus d'un livrable dont les tests ne
   * compilaient pas. Les deux champs se lisent ensemble ou pas du tout.
   */
  verification?: Record<string, unknown> | null;
  /** `non_mesuree` | `verifiee` | `contredite`. */
  qualite?: "non_mesuree" | "partielle" | "verifiee" | "contredite";
}

export interface AutonomousTimelineDTO {
  goal_id: string;
  status: string;
  timeline: { event: string; timestamp: number; decisions: string[] }[];
}

export interface AutonomousStatusDTO {
  total_goals: number;
  active: number;
  completed: number;
  failed: number;
  cancelled: number;
  total_executions: number;
  active_sessions: number;
  interpreter: { history: number };
  decisions: {
    total_decisions: number;
    by_type: Record<string, number>;
    avg_confidence: number;
  };
  guard: {
    total_blocked: number;
    security_connected: boolean;
    policy_connected: boolean;
  };
  memory_loop: { missions: number; success_rate: number; total_lessons: number };
}

export const autonomousClient = {
  status: () => fetchJSON<AutonomousStatusDTO>("/autonomous/status"),
  start: (userRequest: string, context?: Record<string, unknown>) =>
    fetchJSON<AutonomousGoalDTO>("/autonomous/start", {
      method: "POST",
      body: JSON.stringify({ user_request: userRequest, context: context ?? {} }),
    }),
  goal: (goalId: string) =>
    fetchJSON<AutonomousGoalDTO>(`/autonomous/${goalId}`),
  /** GET /autonomous/goals — every goal the engine still holds, newest
   *  first (HOS-102). Before this, a goal was reachable only through the id
   *  returned by `start`, so a running goal became unreachable the moment
   *  the Center that launched it unmounted. */
  goals: () =>
    fetchJSON<{ success: boolean; goals: AutonomousGoalDTO[]; total: number }>(
      "/autonomous/goals",
    ),
  report: (goalId: string) =>
    fetchJSON<AutonomousReportDTO>(`/autonomous/${goalId}/report`),
  timeline: (goalId: string) =>
    fetchJSON<AutonomousTimelineDTO>(`/autonomous/${goalId}/timeline`),
  pause: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/pause`, {
      method: "POST",
    }),
  resume: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/resume`, {
      method: "POST",
    }),
  cancel: (goalId: string) =>
    fetchJSON<{ success: boolean; goal_id: string }>(`/autonomous/${goalId}/cancel`, {
      method: "POST",
    }),
};

// ── Model Intelligence (HOS-060) ──────────────────────────
// model-intelligence-center.tsx rendered MOCK_MODELS and MOCK_DECISIONS while
// these endpoints served six real models and real routing decisions.

export interface ModelIntelligenceDTO {
  success: boolean;
  data: {
    total_models: number;
    total_runs: number;
    average_success_rate: number;
    models: Record<string, unknown>[];
  };
}

export interface ModelRankingEntryDTO {
  model_id: string;
  name: string;
  score: number;
  parameters_b: number;
  vram_mb: number;
  tps: number;
  success_rate: number;
  tags: string[];
}

/** Une mesure réelle sur un axe : le verdict, sa note, et de quoi la
 *  justifier. `score` vaut null quand l'axe ne se juge pas en pourcentage
 *  (le code rend un palier atteint, pas un taux). */
export interface BenchAxisDTO {
  score: number | null;
  verdict: string;
  detail: Record<string, unknown>;
  measured_at: number;
  runtime_version: string;
}

export interface BenchCatalogueEntryDTO {
  model: string;
  measured_at: number;
  axes: Record<string, BenchAxisDTO>;
  /** Note sur 100 par axe. `null` = axe non mesuré — à ne jamais afficher
   *  comme un zéro, sinon un modèle jamais testé passe pour mauvais. */
  notes: Record<string, number | null>;
}

export interface BenchCatalogueDTO {
  success: boolean;
  axes: string[];
  models: BenchCatalogueEntryDTO[];
  total: number;
}

export interface ModelDecisionDTO {
  model_id: string;
  model_name: string;
  runtime: string;
  quantization: string;
  confidence: number;
  reason: string;
  estimated_latency_ms: number;
  estimated_tps: number;
  estimated_vram_mb: number;
  alternatives: { model_id: string; name: string; score: number; reason: string }[];
}

// OpenRouter free-model cloud escalation (HOS-066C) — read-only status:
// whether a key is configured, whether Aegis authorizes it *right now* at
// the current autonomy level, and the real cached catalogue/quota state.
export interface CloudStatusDTO {
  success: boolean;
  configured: boolean;
  authorized: boolean;
  message: string;
  catalog_size?: number;
  catalog_age_s?: number | null;
  quota_remaining?: number | null;
  quota_checked_age_s?: number | null;
  reserve_daily_requests?: number;
}

// HOS-071 Phase D: real cross-runtime/quantization comparison for one
// model — ModelRuntimeOptimizer's own real combinatorial search, wired to
// a route (GET /models/optimize) for the first time.
export interface RuntimeComparisonDTO {
  runtime: string;
  quantization: string;
  estimated_vram_mb: number;
  estimated_tokens_per_second: number;
  risk_level: "low" | "medium" | "high";
  feasible: boolean;
}

export interface OptimizeResultDTO {
  success: boolean;
  model_id?: string;
  comparisons?: RuntimeComparisonDTO[];
  best?: RuntimeComparisonDTO;
  error?: string;
}

export interface ModelHistoryEntryDTO {
  model_id: string;
  model_name: string;
  runtime: string;
  confidence: number;
  reason: string;
  estimated_latency_ms: number;
}

export interface BenchmarkResultDTO {
  benchmark_id: string;
  model_id: string;
  task_type: string;
  latency_ms: number;
  tokens_per_second: number;
  vram_usage_mb: number;
  quality_score: number;
}

export const modelIntelligenceClient = {
  models: () => fetchJSON<ModelIntelligenceDTO>("/models"),
  // limit=100 explicit (HOS-073): the route's own default silently
  // truncated to 5, hiding most registered models regardless of how many
  // were really available — explicit here so a future default change
  // can't quietly reintroduce that.
  ranking: () =>
    fetchJSON<{ success: boolean; models: ModelRankingEntryDTO[] }>("/models/ranking?limit=100"),
  performance: () => fetchJSON<ModelIntelligenceDTO>("/models/performance"),
  history: (limit = 50) =>
    fetchJSON<{ success: boolean; decisions: ModelHistoryEntryDTO[] }>(
      `/models/history?limit=${limit}`,
    ),
  benchmarks: (modelId?: string) =>
    fetchJSON<{ success: boolean; benchmarks: BenchmarkResultDTO[] }>(
      `/models/benchmarks${modelId ? `?model_id=${encodeURIComponent(modelId)}` : ""}`,
    ),
  runBenchmark: (payload: { model_id: string; task_type: string }) =>
    fetchJSON<{ success: boolean; benchmark?: BenchmarkResultDTO }>("/models/benchmark", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  // "task_description" is the documented/route-shape key; earlier code sent
  // "description", which the route silently dropped (HOS-071 Phase C) — the
  // route now accepts both, but new callers should use the documented name.
  recommend: (payload: { task_type?: string; task_description: string; max_vram_mb?: number }) =>
    fetchJSON<{ success: boolean; decision: ModelDecisionDTO }>("/models/recommend", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  optimize: (modelId: string) =>
    fetchJSON<OptimizeResultDTO>(`/models/optimize?model_id=${encodeURIComponent(modelId)}`),
  cloudStatus: () => fetchJSON<CloudStatusDTO>("/models/cloud/status"),
  // Le catalogue mesuré (HOS-108) — distinct de `ranking`, qui rend les
  // heuristiques du ModelProfiler. Ici, uniquement ce qui a été observé.
  catalogue: () => fetchJSON<BenchCatalogueDTO>("/models/catalogue"),
};

// ── Conversation (HOS-062) ────────────────────────────────
// conversation-center.tsx held a module-level `mockSessionId` built from
// Math.random(), a generateMockResponse() that keyword-matched the user's text
// to canned French replies with invented confidence scores, and fake 800–1400 ms
// delays to look like thinking. /api/v1/conversation performs real intent
// classification and real approval gating (R-002 P3).

export interface ConversationIntentDTO {
  type: string;
  confidence: number;
  domain: string;
}

export interface ConversationReplyDTO {
  success: boolean;
  session_id: string;
  message: { role: string; content: string; timestamp: string };
  intent: ConversationIntentDTO | null;
  requires_approval: boolean;
  approval_request: { action: string; risk: string; description: string } | null;
  suggested_actions?: { label: string; action: string }[];
  status: string;
}

export interface ConversationSessionDTO {
  success: boolean;
  session_id: string;
  messages: {
    role: string;
    content: string;
    timestamp: string;
    agent_id?: string;
    mission_id?: string;
  }[];
}

/** One row of GET /conversation/sessions. `title` is derived server-side
 *  from the conversation's first user message and stored, so listing never
 *  loads a transcript (HOS-101). It is empty for a session nobody has
 *  spoken in yet — the caller decides what to show instead. */
export interface ConversationSummaryDTO {
  session_id: string;
  user_id: string;
  status: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export const conversationClient = {
  start: (userRequest?: string) =>
    fetchJSON<{ success: boolean; session_id: string; status: string }>(
      "/conversation/start",
      { method: "POST", body: JSON.stringify({ user_request: userRequest ?? "" }) },
    ),
  sessions: () =>
    fetchJSON<{ success: boolean; sessions: ConversationSummaryDTO[]; total: number }>(
      "/conversation/sessions",
    ),
  /** Erase a conversation, in memory and on disk (HOS-101). Transcripts now
   *  outlive the process, so there has to be a way out of them. */
  remove: (sessionId: string) =>
    fetchJSON<{ success: boolean; deleted: boolean; session_id: string }>(
      `/conversation/${sessionId}`,
      { method: "DELETE" },
    ),
  session: (sessionId: string) =>
    fetchJSON<ConversationSessionDTO>(`/conversation/${sessionId}`),
  message: (sessionId: string, message: string) =>
    fetchJSON<ConversationReplyDTO>("/conversation/message", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, message }),
    }),
  approve: (sessionId: string) =>
    fetchJSON<ConversationReplyDTO>(`/conversation/${sessionId}/approve`, {
      method: "POST",
    }),
  cancel: (sessionId: string) =>
    fetchJSON<ConversationReplyDTO>(`/conversation/${sessionId}/cancel`, {
      method: "POST",
    }),
  context: (sessionId: string) =>
    fetchJSON<ConversationContextResponseDTO>(`/conversation/${sessionId}/context`),
  /** Bind (projectId set) or unbind (projectId null) this session's
   *  active workspace. Filesystem tools only appear in the next /stream
   *  call once this has been called with a project that is ACTIVE and
   *  validation_status="valid" — see backend/conversation/routes.py. */
  bindProject: (sessionId: string, projectId: string | null) =>
    fetchJSON<{ success: boolean; session_id: string; active_project_id: string }>(
      `/conversation/${sessionId}/project`,
      { method: "POST", body: JSON.stringify({ project_id: projectId }) },
    ),
};

/** GET /conversation/{id}/context — the conversation's actual linked state
 *  (mission, agents, runtime, model, workspace, security), distinct from
 *  the token-count estimate ContextMeter shows next to the composer. This
 *  endpoint has existed since the conversation subsystem was built and had
 *  no caller anywhere in the Cockpit before the "/context" slash command. */
export interface ConversationContextResponseDTO {
  success: boolean;
  session_id: string;
  error?: string;
  context?: {
    active_goal_id: string | null;
    active_mission_id: string | null;
    active_project_id: string | null;
    active_agents: string[];
    current_runtime: string | null;
    current_model: string | null;
    workspace_status: string | null;
    security_level: string | null;
    recent_events: unknown[];
  };
}

// ── Workspace (P-001) ─────────────────────────────────────
// Le backend expose la création, le verrouillage, la libération et la
// suppression d'espaces de travail depuis HOS-047 ; aucun écran ne les
// atteignait.

export interface WorkspaceDTO {
  workspace_id: string;
  mission_id?: string;
  agent_id?: string;
  status?: string;
  path?: string;
  locked?: boolean;
  created_at?: string;
}

export const workspaceClient = {
  list: () =>
    fetchJSON<unknown>("/workspace").then((d) => unwrap<WorkspaceDTO>(d, "workspaces")),
  get: (id: string) => fetchJSON<WorkspaceDTO>(`/workspace/${id}`),
  status: (id: string) => fetchJSON<Record<string, unknown>>(`/workspace/${id}/status`),
  artifacts: (id: string) =>
    fetchJSON<unknown>(`/workspace/${id}/artifacts`).then((d) =>
      unwrap<Record<string, unknown>>(d, "artifacts")),
  create: (data: Record<string, unknown>) =>
    fetchJSON<WorkspaceDTO>("/workspace", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  lock: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}/lock`, { method: "POST" }),
  release: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}/release`, { method: "POST" }),
  remove: (id: string) =>
    fetchJSON<Record<string, unknown>>(`/workspace/${id}`, { method: "DELETE" }),
};

// ── Projects & Git (P-002 legacy routes, mounted since HOS-066B under
// /api/v1/projects and /api/v1/git/* via mount_legacy_under_api, but never
// given a Cockpit surface) ──
//
// A "GitHub repo" here is just a local checkout whose git remote points at
// GitHub — there is no separate OAuth/API integration to build. git_tools.py
// shells real git (status/log/branches/diff) and, for create_pull_request,
// the real `gh` CLI, gated through Aegis (git_critical: mandatory
// validation). Linking a project is exactly "give Hermes a local folder
// path"; nothing about it is simulated.

export interface ProjectDTO {
  id: string;
  name: string;
  description: string;
  root_path: string | null;
  // Independent of root_path — both can be set together (HOS-08x
  // Workspace/Filesystem tool layer), mirroring Mission's existing
  // local_path/repository/branch binding rather than one-or-the-other.
  repository: string | null;
  branch: string | null;
  status: string;
  // Real, on-disk-tested state — never set from the frontend. "unvalidated"
  // until POST /projects/{id}/validate actually probes root_path.
  validation_status: "unvalidated" | "valid" | "invalid" | null;
  validated_accessible: boolean | null;
  validated_readable: boolean | null;
  validated_writable: boolean | null;
  validation_detail: string | null;
  validated_at: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export const projectsClient = {
  list: () => fetchJSON<ProjectDTO[]>("/projects"),
  create: (data: {
    name: string; description?: string; root_path?: string;
    repository?: string; branch?: string; tags?: string[];
  }) =>
    fetchJSON<ProjectDTO>("/projects", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: {
    name?: string; description?: string; root_path?: string;
    repository?: string; branch?: string; status?: string; tags?: string[];
  }) =>
    fetchJSON<ProjectDTO>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  validate: (id: string) =>
    fetchJSON<ProjectDTO>(`/projects/${id}/validate`, { method: "POST" }),
  remove: (id: string) =>
    fetchJSON<{ deleted: boolean; id: string }>(`/projects/${id}`, { method: "DELETE" }),
};

// ── Filesystem browse (read-only, directories only — Phase 10's "add a
// workspace" folder picker). Not Aegis-gated: there is nothing yet to
// check against before a folder is registered as a Project. Selecting a
// result here only pre-fills the create-project form. ──

export interface FilesystemBrowseDTO {
  path: string | null;
  parent: string | null;
  directories: string[];
}

export const filesystemBrowseClient = {
  browse: (path?: string) =>
    fetchJSON<FilesystemBrowseDTO>(
      `/filesystem/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`,
    ),
};

export interface GitStatusDTO {
  branch: string;
  detached: boolean;
  dirty: boolean;
  staged: string[];
  modified: string[];
  untracked: string[];
  ahead: number;
  behind: number;
  protected: boolean;
}

export interface GitWriteResultDTO {
  applied: boolean;
  operation: string;
  verdict: string;
  reason: string;
  output: string;
  detail: Record<string, unknown>;
}

export const gitClient = {
  status: (repoPath: string) =>
    fetchJSON<GitStatusDTO>(`/git/status?repo_path=${encodeURIComponent(repoPath)}`),
  createPullRequest: (data: { repo_path: string; title: string; body: string; base?: string }) =>
    fetchJSON<GitWriteResultDTO>("/git/pull-request", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Verification ──────────────────────────────────────────
// Ces routes vivaient hors de /api/v1 et exigeaient une base secondaire.
// P-002 les republie sous le namespace canonique : le client n'a plus qu'une
// seule racine, comme tous les autres.

export interface VerificationRunnerDTO {
  name: string;
  kind: string;
  description: string;
}

export interface VerificationRunRequest {
  repo_path: string;
  runner: string;
  timeout?: number;
  project_id?: string;
}

export interface VerificationRunResult {
  ran: boolean;
  runner: string;
  kind: string;
  passed: boolean;
  exit_code: number | null;
  timed_out: boolean;
  verdict: string;
  reason: string;
  duration_seconds: number;
  output: string;
}

export const verificationClient = {
  runners: () =>
    fetchJSON<unknown>("/verification/runners").then((d) =>
      Array.isArray(d) ? (d as VerificationRunnerDTO[]) : []),
  // POST /verification/run — its payload *is* documented (VerificationRunRequest
  // in backend/api/routes/verification.py, visible at GET /openapi.json), unlike
  // what ValidationCenter used to claim. At the shipped autonomy_level of "low"
  // Aegis will refuse most calls (verdict != "allow", ran=false) — that refusal
  // is the real, honest answer, not a reason to hide the trigger.
  run: (data: VerificationRunRequest) =>
    fetchJSON<VerificationRunResult>("/verification/run", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Monitoring (P-001) ────────────────────────────────────

export const monitoringClient = {
  resources: () => fetchJSON<ResourceStatus>("/runtime/resources"),
  allocations: () =>
    fetchJSON<unknown>("/runtime/resources/allocations").then((d) =>
      unwrap<Record<string, unknown>>(d, "allocations")),
  runtimeEvents: (limit = 50) =>
    fetchJSON<unknown>(`/runtime/events?limit=${limit}`).then((d) =>
      unwrap<Record<string, unknown>>(d, "events")),
  intelligenceScores: () => fetchJSON<Record<string, unknown>>("/runtime/intelligence/scores"),
  recommendations: () =>
    fetchJSON<Record<string, unknown>>("/runtime/intelligence/recommendations"),
  executionStatistics: () => fetchJSON<Record<string, unknown>>("/execution/statistics"),
};
