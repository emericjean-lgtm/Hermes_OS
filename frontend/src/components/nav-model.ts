import {
  LayoutDashboard, MessageSquare, Brain, Target, Users, Zap, Code2,
  Database, Sparkles, Wrench, Scale, Radio, FlaskConical, Dna,
  ShieldCheck, LayoutGrid, Rocket, Play, FolderTree,
  CheckCircle2, LineChart, HeartPulse, AudioLines, Clapperboard,
} from "lucide-react";

/** The one navigation model, shared by the rail and the command palette.
 *  Previously the sidebar owned this list privately, which is fine until a
 *  second surface needs it — then the two drift. */
export type NavItem = {
  id: string;
  label: string;
  icon: React.ElementType;
  /** Searched by the command palette alongside the label, so "vram" finds
   *  Runtime even though the word never appears in the menu. */
  keywords?: string;
};

export type NavGroup = {
  label: string;
  /** Section index, rendered as a technical drawing reference (S1…S5). */
  ref: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Pilotage",
    ref: "S1",
    items: [
      { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, keywords: "accueil vue générale overview" },
      { id: "conversation", label: "Assistant", icon: MessageSquare, keywords: "chat discussion prompt" },
      { id: "voice", label: "Voice", icon: AudioLines, keywords: "voix vocal dictee micro synthese parole mains libres" },
      { id: "missions", label: "Missions", icon: Target, keywords: "dag tâches plan" },
      { id: "execution", label: "Execution", icon: Play, keywords: "run exécution tâche" },
      { id: "autonomous", label: "Autonomous", icon: Dna, keywords: "objectif goal autonome" },
      { id: "studio", label: "Studio", icon: Clapperboard, keywords: "video image comfyui generation ltx rendu youtube shorts" },
    ],
  },
  {
    label: "Intelligence",
    ref: "S2",
    items: [
      { id: "models", label: "Models", icon: Brain, keywords: "modèle ollama routage benchmark" },
      { id: "agents", label: "Agents", icon: Users, keywords: "atlas aegis echo kronos veritas" },
      { id: "runtime", label: "Runtime", icon: Zap, keywords: "monitoring evenements deployment ram flux vram gpu ollama ressources" },
      { id: "code_intelligence", label: "Code Intel", icon: Code2, keywords: "analyse code klaatcode" },
      { id: "skills", label: "Skills", icon: Sparkles, keywords: "compétences capacités" },
      { id: "tools", label: "Tools", icon: Wrench, keywords: "outils mcp connecteurs" },
    ],
  },
  {
    label: "Connaissance",
    ref: "S3",
    items: [
      { id: "memory", label: "Memory", icon: Database, keywords: "mémoire graphe rag alexandrie documents" },
      { id: "workspace", label: "Workspace", icon: FolderTree, keywords: "fichiers artefacts sandbox git" },
    ],
  },
  {
    label: "Gouvernance",
    ref: "S4",
    items: [
      { id: "governance", label: "Governance", icon: Scale, keywords: "approbations règles audit policy" },
      { id: "security", label: "Security", icon: ShieldCheck, keywords: "aegis permissions sécurité" },
      { id: "validation", label: "Validation", icon: CheckCircle2, keywords: "vérification tests qualité" },
      { id: "evolution", label: "Evolution", icon: FlaskConical, keywords: "auto-amélioration propositions" },
    ],
  },
  {
    label: "Opérations",
    ref: "S5",
    items: [
      { id: "system", label: "System", icon: LayoutGrid, keywords: "sante health assemblage composants dependances système statistiques" },
    ],
  },
];

export const ALL_NAV_ITEMS: (NavItem & { group: string })[] = NAV_GROUPS.flatMap((g) =>
  g.items.map((i) => ({ ...i, group: g.label })),
);

export function navLabel(id: string): string {
  return ALL_NAV_ITEMS.find((i) => i.id === id)?.label ?? id;
}

export function navGroupOf(id: string): string {
  return ALL_NAV_ITEMS.find((i) => i.id === id)?.group ?? "";
}
