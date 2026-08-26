"use client";

import {
  AlertTriangle, CheckCircle2, FileWarning, MinusCircle, TestTube2,
  Database, PackageX, CornerUpLeft, FileCode2,
} from "lucide-react";
import type { MissionVerification, VerificationDefect } from "@/types/hermes";

/**
 * Ce que le disque dit, à côté de ce que la mission raconte (HOS-174).
 *
 * La vérification produit treize champs. L'écran en montrait **deux** :
 * « contredite » ou « vérifiée », et un compte de fichiers. Les cinq
 * défauts qu'elle sait nommer — livrable vide, SQL cassé, test qui ne peut
 * pas échouer, dépendance fabriquée, import invalide — n'avaient aucune
 * surface, alors que chacun porte le fichier, la ligne et la raison.
 *
 * C'est le défaut que ce dépôt nomme lui-même à propos des Centers : des
 * capacités implémentées, exportées, et que rien n'importe. Un opérateur
 * lisait « le disque contredit ce rapport » sans jamais savoir en quoi.
 *
 * ## Pourquoi les défauts passent avant le reste
 *
 * Une mission qui a écrit quarante fichiers et dont les tests ne peuvent
 * pas rougir n'est pas « presque bonne ». La règle de ce projet est qu'un
 * succès ne se croit pas sur parole ; l'écran la suit en montrant d'abord
 * ce qui contredit, et seulement ensuite ce qui a bougé.
 */

type Defaut = {
  cle: keyof MissionVerification;
  titre: string;
  icone: React.ElementType;
  /** Comment lire le dict que le backend renvoie pour ce défaut. */
  ligne: (d: VerificationDefect) => string;
};

/** L'ordre est celui du coût : ce qui invalide la preuve d'abord. */
const DEFAUTS: Defaut[] = [
  {
    cle: "test_tautologique",
    titre: "Test qui ne peut pas échouer",
    icone: TestTube2,
    ligne: (d) =>
      `${d.fichier}:${d.ligne} — ${d.fonction ? `${d.fonction}(), ` : ""}${d.raison ?? ""}`,
  },
  {
    cle: "livrable_vide",
    titre: "Livrable vide",
    icone: FileWarning,
    ligne: (d) => `${d.fichier} — « ${d.apercu ?? ""} »`,
  },
  {
    cle: "sql_casse",
    titre: "SQL qui ne s'exécute pas",
    icone: Database,
    ligne: (d) => `${d.fichier} — ${d.motif ?? ""}`,
  },
  {
    cle: "faux_paquet",
    titre: "Dépendance fabriquée",
    icone: PackageX,
    ligne: (d) =>
      `${d.chemin ?? d.fichier} porte le nom du paquet tiers « ${d.paquet ?? ""} »`,
  },
  {
    cle: "imports_remontent",
    titre: "Import relatif invalide",
    icone: CornerUpLeft,
    ligne: (d) =>
      `${d.fichier}:${d.ligne} — remonte de ${d.niveau} niveau(x) pour une profondeur de ${d.profondeur}`,
  },
];

export function VerificationReport({ v }: { v: MissionVerification | null | undefined }) {
  if (v == null) {
    return (
      <Bandeau ton="neutre" icone={MinusCircle}>
        Aucune vérification disque — cette mission n&apos;a pas de workspace lié,
        il n&apos;y a donc rien à comparer. Une absence de mesure n&apos;est pas un
        succès.
      </Bandeau>
    );
  }

  const defauts = DEFAUTS.flatMap((d) => {
    const brut = v[d.cle] as VerificationDefect | null | undefined;
    return brut ? [{ ...d, valeur: brut }] : [];
  });

  const testsEchouent = v.tests?.ran === true && v.tests?.passed === false;
  const manquants = v.manifeste?.manquants ?? [];
  const touches =
    (v.created?.length ?? 0) + (v.modified?.length ?? 0) + (v.deleted?.length ?? 0);

  const contredite = v.contradicted || defauts.length > 0 || testsEchouent;

  return (
    <div className="flex flex-col gap-2">
      <Bandeau
        ton={contredite ? "alarme" : "confirme"}
        icone={contredite ? AlertTriangle : CheckCircle2}
      >
        {contredite ? (
          <>
            La mesure contredit ce rapport. Un succès annoncé au-dessus d&apos;un
            défaut n&apos;est pas un succès.
          </>
        ) : (
          <>
            Confirmé sur le disque : {touches} fichier(s) touché(s)
            {v.workspace ? ` dans ${v.workspace}` : ""}.
          </>
        )}
      </Bandeau>

      {defauts.map(({ cle, titre, icone: Icone, ligne, valeur }) => (
        <Defaut key={String(cle)} icone={Icone} titre={titre}>
          {ligne(valeur)}
        </Defaut>
      ))}

      {testsEchouent && (
        <Defaut icone={TestTube2} titre="Tests du livrable en échec">
          {(v.tests?.output ?? "").trim().split("\n").slice(-1)[0] ||
            "Le runner a rendu un code non nul."}
        </Defaut>
      )}

      {manquants.length > 0 && (
        <Defaut icone={FileCode2} titre="Livrables annoncés et absents">
          {manquants.join(", ")}
        </Defaut>
      )}

      <Mesures v={v} touches={touches} />
    </div>
  );
}

/* ── Le relevé, toujours affiché ────────────────────────────────────── */

function Mesures({ v, touches }: { v: MissionVerification; touches: number }) {
  const tests =
    v.tests?.ran === true
      ? v.tests.passed
        ? "passés"
        : "en échec"
      : v.tests?.reason ?? "non lancés";

  return (
    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 rounded border border-hermes-border/50 bg-hermes-bg px-2.5 py-2">
      <Mesure label="Créés" valeur={String(v.created?.length ?? 0)} />
      <Mesure label="Modifiés" valeur={String(v.modified?.length ?? 0)} />
      <Mesure label="Supprimés" valeur={String(v.deleted?.length ?? 0)} />
      <Mesure label="Tests" valeur={tests} />
      {v.manifeste?.declares != null && (
        <Mesure
          label="Manifeste"
          valeur={`${v.manifeste.declares - (v.manifeste.manquants?.length ?? 0)}/${v.manifeste.declares}`}
        />
      )}
      {touches === 0 && (
        <Mesure label="Disque" valeur="intact" ton="alarme" />
      )}
    </dl>
  );
}

function Mesure({
  label, valeur, ton = "normal",
}: { label: string; valeur: string; ton?: "normal" | "alarme" }) {
  return (
    <div className="min-w-0">
      <dt className="tech-label text-hermes-dim leading-none">{label}</dt>
      <dd
        className={`num text-[11px] leading-tight truncate ${
          ton === "alarme" ? "text-hermes-alarm" : "text-hermes-text"
        }`}
        title={valeur}
      >
        {valeur}
      </dd>
    </div>
  );
}

/* ── Primitives ─────────────────────────────────────────────────────── */

function Bandeau({
  ton, icone: Icone, children,
}: {
  ton: "neutre" | "confirme" | "alarme";
  icone: React.ElementType;
  children: React.ReactNode;
}) {
  const styles = {
    neutre: "text-hermes-muted border-hermes-border/50 bg-hermes-bg",
    confirme: "text-hermes-text border-hermes-arc/35 bg-hermes-arc/[0.07]",
    alarme: "text-hermes-alarm border-hermes-alarm/35 bg-hermes-alarm/[0.08]",
  }[ton];

  return (
    <p className={`flex items-start gap-2 rounded border px-2.5 py-2 text-[10px] leading-relaxed ${styles}`}>
      <Icone size={12} className="mt-[1px] shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

function Defaut({
  icone: Icone, titre, children,
}: { icone: React.ElementType; titre: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded border border-hermes-alarm/25 bg-hermes-alarm/[0.05] px-2.5 py-2">
      <Icone size={12} className="mt-[2px] shrink-0 text-hermes-alarm" />
      <div className="min-w-0">
        <div className="text-[10px] font-medium text-hermes-alarm leading-tight">
          {titre}
        </div>
        <div className="num text-[10px] text-hermes-muted leading-relaxed break-all">
          {children}
        </div>
      </div>
    </div>
  );
}
