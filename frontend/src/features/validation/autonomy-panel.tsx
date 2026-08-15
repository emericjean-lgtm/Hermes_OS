"use client";

import { useAutonomy, useSetAutonomy } from "@/hooks/use-api";
import { Badge, Button, Card } from "@/components/ui/card";

/**
 * Le curseur d'autonomie (§17.5).
 *
 * Les quatre niveaux existaient depuis le début et Aegis les appliquait,
 * mais rien ne les exposait : savoir lequel s'appliquait demandait de lire
 * `config/security.yaml`, et en changer demandait de l'éditer puis de
 * redémarrer. Un garde-fou qu'on ne peut pas régler pendant qu'on travaille
 * finit réglé une fois pour toutes, au niveau le plus permissif dont on a
 * eu besoin un jour (HOS-115).
 *
 * Deux choix d'affichage qui ne sont pas cosmétiques :
 *
 * - **Ce que chaque niveau change est écrit à côté de son bouton**, et le
 *   texte vient du backend. Un cran de sécurité qu'on déplace sans savoir
 *   ce qu'il autorise n'est pas un réglage, c'est un pari.
 * - **La liste des catégories qu'aucun niveau ne débloque est visible en
 *   permanence.** Sans elle, un curseur poussé au maximum laisserait croire
 *   que plus rien ne demandera de validation — ce qui est faux : le §17.3
 *   ne se contourne à aucun niveau, et le promettre serait pire que de ne
 *   rien afficher.
 */
export function AutonomyPanel() {
  const autonomy = useAutonomy();
  const setAutonomy = useSetAutonomy();

  const data = autonomy.data;
  const courant = data?.level ?? "";

  return (
    <Card className="mb-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h3 className="text-hermes-text font-medium">Niveau d&apos;autonomie</h3>
          <p className="text-hermes-muted text-sm mt-1">
            Ce qu&apos;Aegis laisse passer sans te demander. §17.5
          </p>
        </div>
        {data?.overridden && (
          <Button
            onClick={() => setAutonomy.mutate(null)}
            disabled={setAutonomy.isPending}
          >
            Revenir à la configuration
          </Button>
        )}
      </div>

      {autonomy.isError && (
        <p className="text-hermes-danger text-sm">
          Niveau indisponible : {String(autonomy.error)}
        </p>
      )}

      <div className="flex flex-col gap-2">
        {(data?.levels ?? []).map((niveau) => {
          const actif = niveau.name === courant;
          return (
            <button
              key={niveau.name}
              type="button"
              onClick={() => setAutonomy.mutate(niveau.name)}
              disabled={setAutonomy.isPending || actif}
              aria-pressed={actif}
              className={[
                "text-left rounded-md border px-3 py-2 transition-colors",
                actif
                  ? "border-hermes-accent bg-hermes-accent/10"
                  : "border-hermes-border hover:border-hermes-accent/50",
              ].join(" ")}
            >
              <span className="flex items-center gap-2">
                <span className="text-hermes-text font-medium">{niveau.name}</span>
                {actif && <Badge>en vigueur</Badge>}
              </span>
              <span className="block text-hermes-muted text-sm mt-1">
                {niveau.effect}
              </span>
            </button>
          );
        })}
      </div>

      {setAutonomy.isError && (
        <p className="text-hermes-danger text-sm mt-3">
          Changement refusé : {String(setAutonomy.error)}
        </p>
      )}

      {(data?.always_validated ?? []).length > 0 && (
        <div className="mt-4 pt-4 border-t border-hermes-border">
          <p className="text-hermes-muted text-sm">
            Quel que soit le niveau, ces actions demandent toujours ta
            validation (§17.3) :
          </p>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {(data?.always_validated ?? []).map((categorie) => (
              <Badge key={categorie}>{categorie}</Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
