"use client";

/**
 * La console d'opérations (HOS-235).
 *
 * ## Ce qu'elle montre, et d'où ça vient
 *
 * Les jalons 5 à 16 ont produit un registre de runs, des contrats, des
 * points de reprise, un courtier de quotas, des portées d'approbation et
 * un moteur de mise à jour. HOS-234 les a exposés en huit routes `GET`.
 * **Rien ne les affichait.**
 *
 * Chaque section nomme sa source Hermes, et c'est affiché. Ce n'est pas
 * de la décoration : ce Cockpit a déjà eu des compteurs fabriqués —
 * `deployment-center` dormait 1 500 ms puis rendait un nombre tiré au
 * hasard — et une vue qui nomme ses sources rend la fabrication visible
 * au relecteur suivant.
 *
 * ## Le tri-état est visuel, pas seulement logique
 *
 * Quatre choses ne se ressemblent pas ici, parce qu'elles ne veulent pas
 * dire la même chose :
 *
 * - **zéro mesuré** — on a regardé, il n'y en a pas ;
 * - **non mesurable** — la source n'a pas répondu, et on le dit ;
 * - **cause `null`** — aucun indice ne l'a démontrée ;
 * - **cause « inconnue »** — on a cherché sans trouver.
 *
 * Un « on ne sait pas » affiché en `0` est exactement le mensonge que
 * douze jalons ont travaillé à rendre impossible côté serveur. Le refaire
 * à l'affichage l'annulerait.
 *
 * ## Ce qu'elle ne fait pas
 *
 * Aucune écriture, aucune décision. Mission Control est une **vue** du
 * runtime, jamais une seconde autorité : pas d'Aegis bis, pas de moteur
 * d'approbation bis, aucun appel de fournisseur. Le flux d'événements
 * vient de `useCockpitStore`, alimenté par l'unique souscription
 * `FluxEvenements` — surtout pas d'une seconde socket, défaut que
 * HOS-182 a déjà eu à corriger.
 */

import { useMemo, useState } from "react";

import {
  AsyncPanel,
  CenterHeader,
  LiveBadge,
  StatGrid,
} from "@/components/center-scaffold";
import { Badge, Card } from "@/components/ui/card";
import {
  useControlRooms,
  useOperationsApercu,
  useOperationsContrat,
  useOperationsLignee,
} from "@/hooks/use-api";
import { useCockpitStore } from "@/hooks/use-store";
import type {
  Bloc,
  ContratWire,
  ControleWire,
  ControlRoomWire,
  CritereWire,
  RunWire,
} from "@/services/client";

// ── Les quatre façons de ne pas savoir ───────────────────────────────

/** Une section que la source n'a pas pu servir. **Jamais** un zéro.
 *
 *  Un zéro se lit « rien ne s'est passé » ; une indisponibilité se lit
 *  « on ne sait pas ». C'est là que la distinction compte le plus, parce
 *  que c'est là qu'un humain décide. */
function NonMesurable({ source, raison }: { source: string; raison?: string }) {
  return (
    <div className="border border-dashed border-hermes-gold/40 bg-hermes-gold/[0.05] p-3">
      <p className="text-[11px] uppercase tracking-[0.11em] text-hermes-gold">
        Non mesurable
      </p>
      <p className="mt-1 text-xs text-hermes-muted">
        {raison ?? "la source n'a pas répondu"}
      </p>
      <p className="num mt-2 text-[10px] text-hermes-muted/60">{source}</p>
    </div>
  );
}

/** Mesuré, et il n'y en a pas. Distinct du précédent. */
function ZeroMesure({ quoi }: { quoi: string }) {
  return (
    <p className="text-xs text-hermes-muted">
      Aucun {quoi}.{" "}
      <span className="text-hermes-muted/60">Mesuré, pas supposé.</span>
    </p>
  );
}

/** La source, sous chaque section. Petite, mais toujours là. */
function Source({ de }: { de: string }) {
  return (
    <p className="num mt-3 text-[10px] text-hermes-muted/60">source · {de}</p>
  );
}

/** Une cause d'échec, dans ses **trois** états.
 *
 *  `null` — aucun indice ne l'a démontrée (HOS-225). « inconnue » — on a
 *  cherché sans trouver. Une cause nommée — un fait. Les trois
 *  s'affichent différemment, sans quoi le travail du jalon 9 serait perdu
 *  à la dernière étape. */
export function Cause({ cause }: { cause: string | null }) {
  if (cause === null) {
    return (
      <span className="text-[10px] uppercase tracking-[0.11em] text-hermes-muted/70">
        cause non démontrée
      </span>
    );
  }
  if (cause === "inconnue") {
    return <Badge variant="warning">cherchée · non trouvée</Badge>;
  }
  return <Badge variant="danger">{cause}</Badge>;
}

const TON_STATUT: Record<string, "success" | "danger" | "info" | "warning"> = {
  reussi: "success",
  echoue: "danger",
  en_cours: "info",
  en_attente: "default" as "info",
  abandonne: "warning",
  perdu: "warning",
};

function LigneRun({ run }: { run: RunWire }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hermes-border py-2 last:border-0">
      <Badge variant={TON_STATUT[run.statut] ?? "default"}>{run.statut}</Badge>
      <span className="num text-[10px] text-hermes-muted/70">
        {run.identifiant.slice(0, 8)}
      </span>
      {run.tentative > 1 && (
        <Badge variant="info">tentative {run.tentative}</Badge>
      )}
      <span className="min-w-0 flex-1 truncate text-xs text-hermes-text">
        {run.objectif || run.mission || "—"}
      </span>
      {run.modele && (
        <span className="num text-[10px] text-hermes-muted">{run.modele}</span>
      )}
      {run.statut === "echoue" && <Cause cause={run.cause} />}
    </div>
  );
}

/** Rend une section, ou dit pourquoi on ne sait pas. */
function Section<T>({
  bloc,
  vide,
  children,
}: {
  bloc: Bloc<T> | undefined;
  vide: string;
  children: (donnees: T) => React.ReactNode;
}) {
  if (!bloc) return null;
  if (!bloc.disponible || bloc.donnees === null) {
    return <NonMesurable source={bloc.source} raison={bloc.raison} />;
  }
  const donnees = bloc.donnees;
  if (Array.isArray(donnees) && donnees.length === 0) {
    return (
      <div>
        <ZeroMesure quoi={vide} />
        <Source de={bloc.source} />
      </div>
    );
  }
  return (
    <div>
      {children(donnees)}
      <Source de={bloc.source} />
    </div>
  );
}

/** L'état d'un critère, dans ses **quatre** valeurs.
 *
 *  `inverifiable` n'est ni atteint ni non-atteint : c'est une lacune de
 *  mesure, et la ranger avec l'échec ferait passer une ignorance pour un
 *  constat (HOS-221). `viole` est réservé aux non-objectifs — la mission
 *  a fait ce qu'elle s'était interdit, ce qui est un dégât et non un
 *  travail inachevé. */
function EtatCritere({ critere }: { critere: CritereWire }) {
  const variante =
    critere.etat === "atteint"
      ? "success"
      : critere.etat === "viole"
        ? "danger"
        : critere.etat === "inverifiable"
          ? "warning"
          : "default";
  const libelle =
    critere.etat === "inverifiable" ? "invérifiable" : critere.etat.replace("_", " ");
  return <Badge variant={variante}>{libelle}</Badge>;
}

/** La lignée d'un run et le contrat qu'il devait tenir.
 *
 *  C'est la réponse à « avec quel modèle, et pourquoi le premier essai a
 *  raté ? » — la question à laquelle la nuit du 29 au 30 août n'a pas su
 *  répondre sans aller lire un fichier écrasé depuis. */
function DetailDuRun({ run }: { run: string }) {
  const lignee = useOperationsLignee(run);
  const contrat = useOperationsContrat(run);

  return (
    <div className="mt-3 border-l-2 border-hermes-glacier/40 pl-3">
      <p className="text-[10px] uppercase tracking-[0.11em] text-hermes-muted">
        Lignée
      </p>
      <Section bloc={lignee.data as Bloc<RunWire[]> | undefined} vide="tentative">
        {(chaine) => (
          <div className="mt-1">
            {chaine.map((r) => (
              <div key={r.identifiant} className="py-1 text-xs">
                <Badge variant="info">tentative {r.tentative}</Badge>{" "}
                <span className="num text-hermes-muted">{r.statut}</span>{" "}
                {r.modele && (
                  <span className="num text-hermes-muted/70">{r.modele}</span>
                )}
                {r.motif_de_reprise && (
                  <p className="text-hermes-muted/80">
                    reprise : {r.motif_de_reprise}
                  </p>
                )}
                {r.statut === "echoue" && <Cause cause={r.cause} />}
              </div>
            ))}
          </div>
        )}
      </Section>

      <p className="mt-3 text-[10px] uppercase tracking-[0.11em] text-hermes-muted">
        Contrat
      </p>
      <Section
        bloc={contrat.data as Bloc<ContratWire | null> | undefined}
        vide="critère"
      >
        {(c) =>
          c === null ? (
            /* Aucun contrat n'est **déposé** : rien ne dérive aujourd'hui
               un contrat d'un objectif en prose (HOS-229). Le dire, plutôt
               qu'afficher un contrat vide qui se lirait « tenu ». */
            <p className="text-xs text-hermes-muted">
              Aucun contrat déposé pour ce run.
            </p>
          ) : (
            <div className="mt-1 space-y-1 text-xs">
              <p className="text-hermes-muted">{c.resume}</p>
              {c.criteres.map((critere) => (
                <div key={critere.identifiant} className="flex items-center gap-2">
                  <EtatCritere critere={critere} />
                  <span className="text-hermes-text">{critere.texte}</span>
                  {critere.verificateur && (
                    <span className="num ml-auto text-[10px] text-hermes-muted/60">
                      {critere.verificateur}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )
        }
      </Section>
    </div>
  );
}

/** Une Control Room : ce qu'on sait **réellement** d'un agent.
 *
 *  Le taux de réussite y est tri-état, et c'est la raison d'être de ce
 *  composant. `GET /api/v1/agents` rend `success_rate: 100.0` avec
 *  `total_tasks: 0` — un agent qui n'a jamais rien fait, rapporté
 *  parfait — et le Cockpit aggravait avec un `?? 100` et une barre
 *  pleine. Zéro tâche n'est pas cent pour cent : c'est *aucune mesure*,
 *  et un taux affiché sur rien fait choisir un agent sur une réputation
 *  qu'il n'a pas gagnée. */
export function ControlRoom({ salle }: { salle: ControlRoomWire }) {
  const identite = (salle.identite ?? {}) as Record<string, unknown>;
  const capacites = (identite.capabilities as string[] | undefined) ?? [];
  const mission = String(identite.current_mission_id ?? "");

  return (
    <div className="border border-hermes-border p-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-hermes-text">{salle.agent}</span>
        {salle.connu ? (
          <Badge variant={identite.status === "ready" ? "success" : "info"}>
            {String(identite.status ?? "—")}
          </Badge>
        ) : (
          /* Une absence, pas un agent vide. */
          <Badge variant="warning">inconnu du superviseur</Badge>
        )}
      </div>

      {capacites.length > 0 && (
        <p className="num mt-1 text-[10px] text-hermes-muted/70">
          {capacites.join(" · ")}
        </p>
      )}

      <div className="mt-2 flex items-baseline gap-2 text-[10px]">
        <span className="text-hermes-muted">Réussite</span>
        {salle.reussite.mesure ? (
          <span className="num text-hermes-text">
            {salle.reussite.taux}% <span className="text-hermes-muted">({salle.reussite.detail})</span>
          </span>
        ) : (
          /* « — », jamais 100 %. */
          <span className="num text-hermes-muted" title={salle.reussite.detail}>
            — jamais mesuré
          </span>
        )}
      </div>

      <div className="mt-1 flex items-baseline gap-2 text-[10px]">
        <span className="text-hermes-muted">Confiance</span>
        {salle.confiance.score === null ? (
          /* Le moteur de confiance dit déjà « unknown » quand il ne sait
             pas — on le relaie tel quel plutôt que de l'interpréter. */
          <span className="num text-hermes-muted">non disponible</span>
        ) : (
          <span className="num text-hermes-text">
            {salle.confiance.score}/100{" "}
            <span className="text-hermes-muted">({salle.confiance.niveau})</span>
          </span>
        )}
      </div>

      {mission && (
        <p className="num mt-1 text-[10px] text-hermes-glacier">
          mission {mission}
        </p>
      )}

      {salle.runs_en_cours.length > 0 ? (
        <div className="mt-2 border-t border-hermes-border pt-1">
          {salle.runs_en_cours.map((r) => (
            <p key={r.identifiant} className="num text-[10px] text-hermes-muted">
              {r.statut} · {r.identifiant.slice(0, 8)}
            </p>
          ))}
        </div>
      ) : (
        <p className="mt-2 text-[10px] text-hermes-muted/70">
          Aucun run en cours pour cet agent.
        </p>
      )}
    </div>
  );
}

// ── La vue ───────────────────────────────────────────────────────────

export function OperationsCenter() {
  const apercu = useOperationsApercu();
  const salles = useControlRooms();
  // Le run déplié. `null` = aucun : la vue ne devine pas ce que
  // l'opérateur veut voir.
  const [runOuvert, setRunOuvert] = useState<string | null>(null);

  // Le flux vient du store, alimenté par l'unique souscription
  // `FluxEvenements`. Ouvrir une seconde socket ici donnerait deux vues
  // du même bus qui divergeraient à la première coupure — le défaut que
  // HOS-182 a corrigé.
  const evenements = useCockpitStore((s) => s.liveEvents);
  const wsConnecte = useCockpitStore((s) => s.wsConnected);

  /** Filtrés depuis le flux réel, jamais fabriqués.
   *
   *  Si le runtime n'émet rien, la liste reste vide : aucun battement de
   *  cœur, aucune progression inventée. « Une interface moins
   *  spectaculaire mais vraie vaut mieux qu'une interface impressionnante
   *  mais fausse. » */
  const trace = useMemo(
    () =>
      evenements.filter((e) => {
        const t = String(e.type ?? "");
        return (
          t.startsWith("mission.") ||
          t.startsWith("boucle.") ||
          t.startsWith("cloud.") ||
          t.startsWith("maj.") ||
          t.startsWith("execution.") ||
          t.startsWith("filesystem.") ||
          t.startsWith("validation.")
        );
      }),
    [evenements],
  );

  const d = apercu.data;
  const installation = d?.installation.donnees ?? null;
  const fournisseurs = d?.fournisseurs.donnees ?? null;
  const approbations = d?.approbations.donnees ?? null;
  const points = d?.points_de_reprise.donnees ?? null;
  const runs = d?.runs.donnees ?? null;

  /** Un indicateur non mesurable affiche « — », **jamais** zéro.
   *
   *  C'est la règle centrale de cette page, et la seule ligne de code qui
   *  la porte. */
  const chiffre = (valeur: number | null | undefined) =>
    valeur === null || valeur === undefined ? "—" : String(valeur);

  return (
    <div className="space-y-4">
      <CenterHeader
        title="Supervision"
        subtitle="Registre des runs, fournisseurs, approbations, points de reprise, installation"
        right={<LiveBadge connected={wsConnecte} />}
      />

      <StatGrid
        stats={[
          {
            label: "Runs en cours",
            value: chiffre(runs?.nombre_en_cours),
            tone: "ok",
          },
          {
            label: "Approbations",
            value: chiffre(approbations?.en_attente.length),
            tone: "warn",
          },
          {
            label: "Portées vivantes",
            value: chiffre(approbations?.portees_vivantes.length),
            tone: "warn",
          },
          {
            label: "Points de reprise",
            value: chiffre(points?.length),
            tone: "ok",
          },
          {
            label: "Fournisseurs",
            value: chiffre(fournisseurs?.configures.length),
            tone: "ok",
          },
          {
            label: "Santé",
            value: installation
              ? installation.sante.sain
                ? "OK"
                : "ALERTE"
              : "—",
            tone: installation?.sante.sain === false ? "bad" : "ok",
          },
        ]}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <AsyncPanel
          title="Installation"
          subtitle="Version produit, version installée, auto-vérification"
          isLoading={apercu.isLoading}
          isError={apercu.isError}
          error={apercu.error}
          isEmpty={false}
          emptyLabel=""
        >
          <Section bloc={d?.installation} vide="renseignement">
            {(i) => (
              <div className="space-y-2 text-xs">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-hermes-muted">Version du code</span>
                  <span className="num text-hermes-glacier">
                    {i.version_du_code}
                  </span>
                </div>
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-hermes-muted">Version installée</span>
                  {/* `null` n'est ni « 0 » ni la version du code : c'est
                      une installation antérieure au versionnement, et le
                      dire est la seule réponse juste (HOS-232). */}
                  {i.version_installee ? (
                    <span className="num text-hermes-glacier">
                      {i.version_installee}
                    </span>
                  ) : (
                    <span className="text-hermes-muted/70">
                      jamais marquée
                    </span>
                  )}
                </div>
                {i.version_installee &&
                  i.version_installee !== i.version_du_code && (
                    <Badge variant="warning">
                      écart — mise à jour non confirmée
                    </Badge>
                  )}
                <ul className="mt-3 space-y-1">
                  {i.sante.controles.map((c: ControleWire) => (
                    <li key={c.nom} className="flex items-center gap-2">
                      {/* « Sans objet » n'est pas un échec : une
                          installation neuve n'a pas de points de reprise.
                          Le peindre en rouge ferait chercher une panne
                          qui n'existe pas. */}
                      <Badge
                        variant={
                          c.etat === "ok"
                            ? "success"
                            : c.etat === "echec"
                              ? "danger"
                              : "default"
                        }
                      >
                        {c.etat === "indisponible" ? "sans objet" : c.etat}
                      </Badge>
                      <span className="text-hermes-muted">{c.nom}</span>
                      <span className="num ml-auto truncate text-[10px] text-hermes-muted/60">
                        {c.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Section>
        </AsyncPanel>

        <AsyncPanel
          title="Fournisseurs"
          subtitle="Écarts, disjoncteurs et quotas — courtier RAL"
          isLoading={apercu.isLoading}
          isError={apercu.isError}
          error={apercu.error}
          isEmpty={false}
          emptyLabel=""
        >
          <Section bloc={d?.fournisseurs} vide="fournisseur">
            {(f) =>
              f.aucun_configure ? (
                <div className="space-y-1 text-xs">
                  {/* L'état **normal** : aucune clé n'est posée par
                      défaut. Le taire le ferait lire comme une panne. */}
                  <p className="text-hermes-muted">
                    Aucun fournisseur distant configuré.
                  </p>
                  <p className="text-hermes-muted/70">
                    C'est le défaut : sans clé, le cloud est injoignable et
                    tout reste local.
                  </p>
                </div>
              ) : (
                <div className="space-y-2 text-xs">
                  {f.etats.map((e) => (
                    <div key={e.fournisseur} className="flex items-center gap-2">
                      <Badge
                        variant={
                          e.etat === "disponible"
                            ? "success"
                            : e.etat === "ouvert"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {e.etat}
                      </Badge>
                      <span className="text-hermes-text">{e.fournisseur}</span>
                      {e.dans_s > 0 && (
                        <span className="num ml-auto text-[10px] text-hermes-muted">
                          {Math.round(e.dans_s)} s
                        </span>
                      )}
                      {e.raison && (
                        <p className="w-full truncate text-[10px] text-hermes-muted/70">
                          {e.raison}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )
            }
          </Section>
        </AsyncPanel>

        <AsyncPanel
          title="Approbations"
          subtitle="En attente et portées vivantes — Aegis décide, cette vue montre"
          isLoading={apercu.isLoading}
          isError={apercu.isError}
          error={apercu.error}
          isEmpty={false}
          emptyLabel=""
        >
          <Section bloc={d?.approbations} vide="approbation">
            {(a) => (
              <div className="space-y-2 text-xs">
                {/* Séparées, parce qu'une ligne qui autorise un dossier
                    entier ne se lit pas comme une qui autorise une action
                    (HOS-224). */}
                {a.portees_vivantes.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-[10px] uppercase tracking-[0.11em] text-hermes-gold">
                      Portées d'arborescence
                    </p>
                    {a.portees_vivantes.map((p) => (
                      <div
                        key={p.id}
                        className="border border-hermes-gold/30 bg-hermes-gold/[0.05] p-2"
                      >
                        <p className="num text-hermes-gold">
                          {p.action_type} · {p.portee_racine}
                        </p>
                        <p className="mt-0.5 text-hermes-muted">
                          {p.usages_restants ?? "?"} usage(s) restant(s)
                        </p>
                      </div>
                    ))}
                  </div>
                )}
                {a.en_attente.length === 0 ? (
                  <ZeroMesure quoi="approbation en attente" />
                ) : (
                  a.en_attente.slice(0, 8).map((p) => (
                    <div key={p.id} className="border-b border-hermes-border pb-1">
                      <span className="num text-hermes-muted">
                        {p.action_type}
                      </span>{" "}
                      <span className="text-hermes-text">{p.description}</span>
                    </div>
                  ))
                )}
                {a.en_attente.length > 8 && (
                  <p className="text-hermes-muted/70">
                    +{a.en_attente.length - 8} autre(s)
                  </p>
                )}
              </div>
            )}
          </Section>
        </AsyncPanel>

        <AsyncPanel
          title="Points de reprise"
          subtitle="Ce qui permet d'annuler — git ou copie vérifiée"
          isLoading={apercu.isLoading}
          isError={apercu.isError}
          error={apercu.error}
          isEmpty={false}
          emptyLabel=""
        >
          <Section bloc={d?.points_de_reprise} vide="point de reprise">
            {(liste) => (
              <div className="space-y-2 text-xs">
                {liste.slice(0, 8).map((p) => (
                  <div key={p.identifiant} className="border-b border-hermes-border pb-1">
                    <div className="flex items-center gap-2">
                      <Badge variant={p.mecanisme === "git" ? "info" : "default"}>
                        {p.mecanisme}
                      </Badge>
                      <span className="num text-hermes-muted">
                        {p.identifiant.slice(0, 8)}
                      </span>
                      {/* Sans état de mission, il ne ramène que la moitié
                          (HOS-223) — le dire évite de compter dessus. */}
                      {!p.avec_etat && (
                        <Badge variant="warning">fichiers seuls</Badge>
                      )}
                    </div>
                    <p className="truncate text-hermes-muted/80">
                      {p.motif || "—"}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Section>
        </AsyncPanel>
      </div>

      <Card title="Runs en cours" subtitle="Registre des exécutions">
        <Section bloc={d?.runs} vide="run en cours">
          {(r) =>
            r.en_cours.length === 0 ? (
              <ZeroMesure quoi="run en cours" />
            ) : (
              <div>
                {r.en_cours.map((run) => (
                  <div key={run.identifiant}>
                    <button
                      type="button"
                      onClick={() =>
                        setRunOuvert((actuel) =>
                          actuel === run.identifiant ? null : run.identifiant,
                        )
                      }
                      className="w-full text-left"
                      aria-expanded={runOuvert === run.identifiant}
                    >
                      <LigneRun run={run} />
                    </button>
                    {runOuvert === run.identifiant && (
                      <DetailDuRun run={run.identifiant} />
                    )}
                  </div>
                ))}
              </div>
            )
          }
        </Section>
      </Card>

      <AsyncPanel
        title="Control Rooms"
        subtitle="Un agent, ce qu'il exécute, et ce qu'on ne sait pas de lui"
        isLoading={salles.isLoading}
        isError={salles.isError}
        error={salles.error}
        isEmpty={false}
        emptyLabel=""
      >
        <Section bloc={salles.data} vide="agent">
          {(liste) => (
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {liste.map((salle) => (
                <ControlRoom key={salle.agent} salle={salle} />
              ))}
            </div>
          )}
        </Section>
      </AsyncPanel>

      <Card
        title="Trace d'exécution"
        subtitle="Le flux réel du runtime — rien n'est affiché s'il n'émet rien"
        live={wsConnecte}
      >
        {trace.length === 0 ? (
          <p className="text-xs text-hermes-muted">
            Aucun événement d'opération reçu.{" "}
            <span className="text-hermes-muted/70">
              Rien n'est affiché tant que le runtime n'émet rien — pas de
              battement de cœur inventé.
            </span>
          </p>
        ) : (
          <ul className="num max-h-72 space-y-1 overflow-y-auto text-[10px]">
            {trace.slice(0, 80).map((e, i) => (
              <li
                key={`${String(e.timestamp ?? "")}-${i}`}
                className="flex gap-2 border-b border-hermes-border pb-1"
              >
                <span className="shrink-0 text-hermes-muted/60">
                  {String(e.timestamp ?? "").slice(11, 19)}
                </span>
                <span className="shrink-0 text-hermes-glacier">
                  {String(e.type)}
                </span>
                <span className="min-w-0 flex-1 truncate text-hermes-muted">
                  {JSON.stringify(e.payload ?? {}).slice(0, 160)}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Source de="bus d'événements Hermes · souscription unique" />
      </Card>
    </div>
  );
}
