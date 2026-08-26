"use client";

import { useEffect, useMemo, useState } from "react";
import { useCockpitStore } from "@/hooks/use-store";
import { useMissions, useExecutions } from "@/hooks/use-api";
import { POSTURES, type EtatOperateur } from "@/components/operateur";

/**
 * D'où l'opérateur tient sa posture (HOS-182).
 *
 * De topics que le backend publie réellement, et de rien d'autre. La table
 * ci-dessous a été écrite en lisant `collect_known_topics()` sur le backend
 * en marche, pas de mémoire : la première version tapait sur `mission.started`
 * et `files_read`, deux noms qui n'existent pas. Les vrais sont
 * `execution.task_started` et `filesystem.read`.
 *
 * ## Ce qui a fallu réparer d'abord
 *
 * Ces topics-là étaient publiés et **jetés**. La liste blanche de l'EventHub
 * en refusait 35, dont la totalité de `filesystem.*` et de `execution.*` —
 * l'interface ne pouvait donc pas voir une écriture sur disque même en la
 * guettant. Corrigé côté backend (HOS-181), gardé par
 * `backend/tests/test_topics_publies_sont_autorises.py`.
 *
 * ## La règle de repli
 *
 * Quand aucun événement récent ne dit ce qui se passe :
 *
 * * une mission ou une exécution est en cours → `reflexion`. Ce n'est pas
 *   une invention : une tâche est partie et l'on attend le modèle, c'est
 *   littéralement ce qui se passe.
 * * sinon → `repos`.
 *
 * Et si une mission tourne pendant que l'opérateur reste au repos, ce repos
 * **est** l'information : le système n'annonce rien de ce qu'il fait. C'est
 * le défaut que ce projet traque depuis le début, rendu visible au lieu
 * d'être deviné dans un journal.
 *
 * ## Deux postures sans signal
 *
 * `verification` et `tests` n'ont aucun topic correspondant dans les 125 que
 * le backend déclare. Elles restent atteignables par `signalerOperateur()`,
 * qu'un Center appelle quand il sait ce qu'il déclenche, et ne sont jamais
 * inférées d'un événement. Les câbler sur une approximation serait
 * exactement le genre de vraisemblance que ce projet refuse.
 */

interface Regle {
  etat: EtatOperateur;
  /** Combien de temps cet événement continue de décrire le présent. */
  tenue: number;
}

const TABLE: Record<string, Regle> = {
  // ── Fichiers (HOS-181 : jetés avant, invisibles) ──
  "filesystem.read": { etat: "lecture", tenue: 5000 },
  "filesystem.write": { etat: "ecriture", tenue: 5000 },
  "filesystem.create": { etat: "ecriture", tenue: 5000 },
  "filesystem.copy": { etat: "ecriture", tenue: 5000 },
  "filesystem.move": { etat: "ecriture", tenue: 5000 },
  "filesystem.delete": { etat: "ecriture", tenue: 5000 },
  "filesystem.verification_failed": { etat: "defaut", tenue: 8000 },
  "filesystem.permission_denied": { etat: "defaut", tenue: 8000 },

  // ── Exécution de mission ──
  "execution.planning": { etat: "reflexion", tenue: 10000 },
  "execution.started": { etat: "lancement", tenue: 3000 },
  "execution.task_started": { etat: "lancement", tenue: 2500 },
  "execution.task_completed": { etat: "reussite", tenue: 2500 },
  "execution.completed": { etat: "reussite", tenue: 5000 },
  "execution.failed": { etat: "alerte", tenue: 10000 },
  "execution.retry": { etat: "defaut", tenue: 6000 },
  "execution.optimized": { etat: "reflexion", tenue: 4000 },
  "execution.waiting_approval": { etat: "decision", tenue: 120000 },

  // ── Tâches et workflows ──
  "task.created": { etat: "reflexion", tenue: 4000 },
  "task.started": { etat: "lancement", tenue: 2500 },
  "task.update": { etat: "reflexion", tenue: 4000 },
  "task.completed": { etat: "reussite", tenue: 2500 },
  "task.failed": { etat: "alerte", tenue: 10000 },
  "task.cancelled": { etat: "defaut", tenue: 5000 },
  "workflow.started": { etat: "lancement", tenue: 3000 },
  "workflow.completed": { etat: "reussite", tenue: 5000 },
  "workflow.failed": { etat: "alerte", tenue: 10000 },

  // ── Accord humain attendu. Tenue longue : ça attend vraiment. ──
  "security.validation.requested": { etat: "decision", tenue: 120000 },
  "validation.request": { etat: "decision", tenue: 120000 },

  // ── Modèles ──
  "model.switch_started": { etat: "chargement", tenue: 25000 },
  "model.loaded": { etat: "chargement", tenue: 4000 },

  // ── Matériel. Le débordement est un état, pas un geste : il tient
  //    longtemps parce qu'il ne se résout pas tout seul. ──
  "runtime.overloaded": { etat: "debordement", tenue: 20000 },
  "vram.limit_reached": { etat: "debordement", tenue: 20000 },
  "runtime.residency_unsatisfiable": { etat: "debordement", tenue: 20000 },
  "runtime.context_degraded": { etat: "defaut", tenue: 12000 },
  "runtime.failed": { etat: "alerte", tenue: 12000 },
  "runtime.unavailable": { etat: "alerte", tenue: 12000 },

  // ── Autonome ──
  "autonomous.goal.received": { etat: "lancement", tenue: 3000 },
  "autonomous.goal.analyzed": { etat: "reflexion", tenue: 6000 },
  "autonomous.plan.created": { etat: "reflexion", tenue: 6000 },
  "autonomous.decision.made": { etat: "reflexion", tenue: 4000 },
  "autonomous.execution.started": { etat: "lancement", tenue: 3000 },
  "autonomous.execution.completed": { etat: "reussite", tenue: 5000 },
  "autonomous.goal.failed": { etat: "alerte", tenue: 10000 },
  "autonomous.learning.completed": { etat: "lecture", tenue: 4000 },

  // ── Sécurité ──
  "security.permission.denied": { etat: "defaut", tenue: 8000 },
  "security.threat.detected": { etat: "alerte", tenue: 12000 },

  // ── Assistant ──
  "chat.token": { etat: "reflexion", tenue: 3000 },

  // ── Connaissance ──
  "knowledge.indexed": { etat: "lecture", tenue: 4000 },
  "memory.updated": { etat: "lecture", tenue: 4000 },

  // ── Agents de code ──
  "ci.task.started": { etat: "reflexion", tenue: 8000 },
  "ci.task.completed": { etat: "reussite", tenue: 3000 },
  "ci.task.failed": { etat: "alerte", tenue: 8000 },
  "klaatcode.task.started": { etat: "reflexion", tenue: 8000 },
  "klaatcode.patch.generated": { etat: "ecriture", tenue: 5000 },
  "klaatcode.task.completed": { etat: "reussite", tenue: 3000 },
  "klaatcode.task.failed": { etat: "alerte", tenue: 8000 },
  "ohmypi.edit.started": { etat: "ecriture", tenue: 6000 },
  "ohmypi.edit.completed": { etat: "reussite", tenue: 3000 },
  "ohmypi.error": { etat: "alerte", tenue: 8000 },

  // ── Compétences ──
  "skill.generated": { etat: "reussite", tenue: 3000 },
  "skill.compilation.completed": { etat: "reussite", tenue: 3000 },
};

/** Les topics que la table couvre. Exporté pour que les tests puissent
 *  vérifier qu'ils existent bien dans la liste blanche du backend — c'est
 *  côté backend que vivent les vrais noms, et un test frontend qui les
 *  recopierait ne prouverait que sa propre copie. */
export const TOPICS_SUIVIS = Object.keys(TABLE);

/** Les postures qu'un événement peut réellement produire.
 *
 *  `verification` et `tests` en sont absentes, et doivent le rester tant
 *  qu'aucun topic ne les décrit : elles ne s'atteignent que par
 *  `signalerOperateur()`, depuis un Center qui sait ce qu'il déclenche. */
export const ETATS_DEDUITS: ReadonlySet<EtatOperateur> = new Set(
  Object.values(TABLE).map((r) => r.etat),
);

export interface LectureOperateur {
  etat: EtatOperateur;
  libelle: string;
  teinte: string;
  /** Le signal qui a produit cette posture — un nom de topic, ou une des
   *  deux raisons de repli. Affiché sous la figure : il faut pouvoir dire
   *  *pourquoi* elle fait ce qu'elle fait. */
  signal: string;
}

export function useOperateur(): LectureOperateur {
  const liveEvents = useCockpitStore((s) => s.liveEvents);
  const local = useCockpitStore((s) => s.operateurLocal);

  const { data: missions } = useMissions();
  const { data: executions } = useExecutions();

  const [maintenant, setMaintenant] = useState(() => Date.now());

  const enCours = useMemo(() => {
    const m = (missions ?? []).some((x) => x.status === "RUNNING" || x.status === "PLANNING");
    const e = (executions ?? []).some(
      (x) => x.state === "running" || x.state === "planning" || x.state === "validating",
    );
    return m || e;
  }, [missions, executions]);

  // Le plus récent événement qui décrit encore le présent. Le local prime :
  // un onglet qui streame sait ce qu'il fait à la milliseconde, là où le bus
  // ne l'apprendra qu'après coup.
  const { etat, signal, expire } = useMemo(() => {
    if (local && local.expire > maintenant) {
      return { etat: local.etat, signal: local.signal, expire: local.expire };
    }

    for (const ev of liveEvents) {
      const regle = TABLE[ev.type];
      if (!regle) continue;
      const t = Date.parse(ev.timestamp);
      // Un horodatage illisible ne doit pas faire vivre une posture
      // indéfiniment : sans date, l'événement ne prouve rien sur le présent.
      if (!Number.isFinite(t)) continue;
      const fin = t + regle.tenue;
      if (fin > maintenant) return { etat: regle.etat, signal: ev.type, expire: fin };
      // Les événements sont du plus récent au plus ancien : le premier qui
      // a expiré condamne tous les suivants.
      break;
    }

    return enCours
      ? { etat: "reflexion" as EtatOperateur, signal: "exécution en cours", expire: null }
      : { etat: "repos" as EtatOperateur, signal: "aucune activité signalée", expire: null };
  }, [liveEvents, local, maintenant, enCours]);

  // Une seule minuterie, posée à l'instant exact où la posture cesse d'être
  // vraie — plutôt qu'un battement à la seconde qui réveillerait l'arbre
  // soixante fois par minute pour ne rien changer.
  useEffect(() => {
    if (expire === null) return;
    const delai = expire - Date.now();
    if (delai <= 0) {
      setMaintenant(Date.now());
      return;
    }
    const minuteur = setTimeout(() => setMaintenant(Date.now()), delai + 40);
    return () => clearTimeout(minuteur);
  }, [expire]);

  const p = POSTURES[etat];
  return { etat, libelle: p.libelle, teinte: p.teinte, signal };
}
