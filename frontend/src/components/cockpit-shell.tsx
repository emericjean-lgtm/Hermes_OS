"use client";

import { useEffect, useState } from "react";
import { Rail } from "@/components/rail";
import { InstrumentBar } from "@/components/instrument-bar";
import { StatusBar } from "@/components/statusbar";
import { CommandPalette } from "@/components/command-palette";
import { useCockpitStore } from "@/hooks/use-store";
import { CenterBoundary } from "@/components/center-boundary";
import { FluxEvenements } from "@/components/flux-evenements";
import { OperateurDeGarde } from "@/components/operateur-de-garde";
import { RoomHalo } from "@/components/room-halo";
import { DashboardView } from "@/features/dashboard/dashboard-view";
import { MissionCenter } from "@/features/missions/mission-center";
import { AgentCenter } from "@/features/agents/agent-center";
import { RuntimeCenterMerged } from "@/features/runtime/runtime-center-merged";
import { MemoryCenter } from "@/features/memory/memory-center";
// KnowledgeGraphCenter et AlexandrieCenter ne sont plus des vues de premier
// niveau : leur contenu est devenu un onglet du Memory Center, qui affichait
// déjà les mêmes données. Voir features/memory/memory-center.tsx.
import { SkillsCenter } from "@/features/skills/skills-center";
import { ToolsCenter } from "@/features/tools/tools-center";
import { GovernanceCenter } from "@/features/governance/governance-center";
import { AutonomousCenter } from "@/features/autonomous/autonomous-center";
import { CodeIntelligenceCenter } from "@/features/code-intelligence/code-intelligence-center";
import { EvolutionCenter } from "@/features/evolution/evolution-center";
import { SecurityCenter } from "@/features/security/security-center";
import { SystemCenterMerged } from "@/features/system/system-center-merged";
import ConversationCenter from "@/features/conversation/conversation-center";
import { VoiceCenter } from "@/features/voice/voice-center";
import { StudioCenter } from "@/features/studio/studio-center";
import ModelIntelligenceCenter from "@/features/models/model-intelligence-center";
import { WorkspaceCenter } from "@/features/workspace/workspace-center";
import { ExecutionCenter } from "@/features/execution/execution-center";
import { ValidationCenter } from "@/features/validation/validation-center";

/** Every id offered by the rail or the palette must resolve to a Center here.
 *
 *  Eight of these were once implemented, exported and never imported: the
 *  navigation advertised them and clicking any one silently fell through to
 *  the dashboard because `views` had no entry. The `satisfies` below is what
 *  stops that recurring — a nav id with no Center is a type error rather than
 *  a dead menu entry. */
const views = {
  dashboard: DashboardView,
  conversation: ConversationCenter,
  voice: VoiceCenter,
  models: ModelIntelligenceCenter,
  missions: MissionCenter,
  agents: AgentCenter,
  runtime: RuntimeCenterMerged,
  code_intelligence: CodeIntelligenceCenter,
  memory: MemoryCenter,
  skills: SkillsCenter,
  tools: ToolsCenter,
  governance: GovernanceCenter,
  evolution: EvolutionCenter,
  autonomous: AutonomousCenter,
  studio: StudioCenter,
  security: SecurityCenter,
  system: SystemCenterMerged,
  // P-001 : capacités backend qui n'avaient aucun écran.
  workspace: WorkspaceCenter,
  execution: ExecutionCenter,
  validation: ValidationCenter,
  // `policy`, `knowledge` et `alexandrie` ont été fusionnés : Policy
  // interrogeait exactement les mêmes endpoints que Governance, et Memory
  // affichait déjà l'intégralité de Knowledge Graph et d'Alexandrie. Les
  // anciens identifiants restent acceptés pour qu'un lien ou un état
  // persistant pointant dessus n'atterrisse pas silencieusement sur le
  // Dashboard.
  policy: GovernanceCenter,
  knowledge: MemoryCenter,
  alexandrie: MemoryCenter,
} satisfies Record<string, React.FC>;

export default function CockpitShell() {
  const { activeView } = useCockpitStore();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const View = views[activeView as keyof typeof views] ?? DashboardView;
  // The Assistant is a conversation surface, not an operations table: on an
  // ultrawide monitor the usual left-anchored, width-capped wrapper below
  // leaves a large dead zone on the right instead of centering the chat.
  // Every other Center keeps the left-anchored/capped layout on purpose
  // (see the comment on the wrapper) — this is a per-view exception, not a
  // change to that default.
  const isConversation = activeView === "conversation";

  // ⌘K / Ctrl+K anywhere. Bound on the window rather than a focused element
  // so it works no matter which Center currently owns focus.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen text-hermes-text">
      <RoomHalo />
      <Rail onOpenPalette={() => setPaletteOpen(true)} />
      <InstrumentBar onOpenPalette={() => setPaletteOpen(true)} />

      <main
        // Bounded height here with the scroll on the inner pane: without it,
        // a Center built to scroll internally (the Assistant transcript, for
        // one) grows the whole document instead, and anything anchored beside
        // that pane scrolls away with it.
        className="h-screen overflow-hidden transition-[margin-left] duration-200 ease-out"
        style={{
          marginLeft: "var(--rail-w)",
          paddingTop: "var(--bar-h)",
          paddingBottom: "var(--foot-h)",
        }}
      >
        <div className="h-full overflow-y-auto px-6 py-6 2xl:px-10">
          {/* Content is left-anchored inside a generous measure rather than
              centred in the viewport: an operations surface should start
              where the eye lands after the rail, not float in the middle.
              The Assistant is the deliberate exception (isConversation) —
              a conversation reads better centered, using the width an
              ultrawide monitor actually has instead of a fixed left-anchored
              cap. h-full on both wrappers below matters just as much as the
              width: without it, ConversationCenter's own h-full/min-h-0
              transcript and rail never get a bounded height to scroll
              inside, and the whole page scrolls instead (see CenterBoundary
              and ConversationCenter's own comments). */}
          <div className={isConversation ? "mx-auto h-full w-full" : "h-full max-w-[1560px] 2xl:max-w-[1860px]"}>
            <CenterBoundary viewKey={activeView}>
              {/* Pas d'`AnimatePresence` ici, et c'est la correction — pas
                  un oubli (HOS-198).

                  Cette bascule de vue est passée par trois états. Avec
                  `mode="wait"`, toute navigation se bloquait dès que la
                  sortie de l'ancienne vue ne se terminait pas, et rien ne
                  garantit qu'elle se termine : une frame de composition
                  manquée suffit, et `AnimatePresence` attend cette
                  confirmation indéfiniment. Sans `mode` mais avec `exit`,
                  l'ancienne vue restait affichée par-dessus la nouvelle le
                  temps du fondu — visible surtout sur Studio → Graphe,
                  parce qu'une iframe ignore le fondu CSS de ses ancêtres et
                  reste composée à pleine visibilité. Retirer `exit` devait
                  régler ça en faisant démonter l'ancienne vue aussitôt.

                  Ça ne l'a pas fait, et c'est **pire** : sans variante de
                  sortie, `AnimatePresence` (framer-motion 11.18.2, React 19)
                  ne relâche jamais l'enfant sortant. Mesuré sur
                  l'application en marche — chaque navigation ajoutait un
                  `.center-enter` de plus dans le DOM, tous à opacité 1,
                  aucun retiré : Studio, puis Assistant, puis Mission
                  Center, empilés dans le flux. Le premier gardait le haut
                  de la page et les suivants étaient poussés 1 140 px plus
                  bas, hors écran — d'où « je change d'onglet et ça ne
                  fonctionne pas », alors que `activeView` et `aria-current`
                  changeaient correctement.

                  La leçon est qu'`AnimatePresence` n'avait plus de travail :
                  la sortie est retirée pour de bonnes raisons, et l'entrée
                  est une animation CSS (`center-enter`) que le remontage
                  déclenche tout seul. Ne restait que sa comptabilité de
                  présence — laquelle fuyait. Un `key` sur un élément
                  ordinaire suffit : React démonte l'ancienne vue de façon
                  déterministe, sans dépendre d'une frame de composition, et
                  l'iframe s'en va avec elle. */}
              <div
                key={activeView}
                /* `h-full overflow-hidden` reste réservé à l'Assistant :
                   c'est le seul Center qui gère son propre défilement
                   interne (transcript + rail), et qui a donc besoin d'une
                   hauteur bornée pour que son `min-h-0` interne se calcule.
                   Appliqué à tous les autres Centers, ce même couple
                   rognait leur contenu au lieu de le rendre défilable :
                   mesuré sur Governance à 500 px de fenêtre, une boîte de
                   370 px contenait 415 px de contenu réel, et les 45 px
                   manquants n'étaient récupérables nulle part — ni par un
                   scroll interne (aucun Center hors Assistant n'en a un),
                   ni par le scroll de la page (`overflow-hidden` l'en
                   empêchait). `min-h-full`, sans `overflow-hidden`, laisse
                   le contenu déborder jusqu'au `overflow-y-auto` du
                   conteneur parent — dix-sept Centers sur vingt-sept
                   n'ont pas leur propre zone de défilement et dépendaient
                   entièrement de ce débordement pour être consultables. */
                className={
                  isConversation
                    ? "h-full relative overflow-hidden center-enter"
                    : "min-h-full relative center-enter"
                }
              >
                <View />
              </div>
            </CenterBoundary>
          </div>
        </div>
      </main>

      <StatusBar />
      {/* Hors du conteneur de vue ci-dessus, et c'est tout l'intérêt : le
          shell démonte le Center actif à chaque bascule d'onglet, et une
          animation CSS repart de zéro quand son élément est démonté.
          L'opérateur placé ici traverse les bascules sans recommencer son
          geste — ce qui est exact, puisque le système ne s'est pas
          interrompu parce qu'on a regardé ailleurs. */}
      <FluxEvenements />
      <OperateurDeGarde />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
