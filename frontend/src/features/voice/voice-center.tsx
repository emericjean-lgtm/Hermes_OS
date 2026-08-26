"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Mic, MicOff, Volume2, VolumeX, Radio, Check, X, Loader2, Send,
} from "lucide-react";
import { Card, Badge } from "@/components/ui/card";
import { CenterHeader } from "@/components/center-scaffold";
import { useDictee, useSynthese, useVoixFiltrees, LANGUES } from "./use-voice";
import { useCockpitStore } from "@/hooks/use-store";
import { voiceClient, type VoiceCapability, type VoicePreferences } from "@/services/client";

/**
 * Voice Center (HOS-173).
 *
 * Hermes savait déjà dicter — `voice-input.tsx` le fait dans l'Assistant —
 * mais la capacité n'avait ni écran, ni réglage, ni moyen d'être éprouvée.
 * Elle était réelle et invisible.
 *
 * Cet écran fait trois choses, dans cet ordre d'importance :
 *
 *  1. **dire ce qui est disponible**, mesuré et non déclaré. Le serveur
 *     porte quatre classes de fournisseurs depuis HOS-064 dont aucune n'a
 *     sa dépendance ; les annoncer serait répéter la confusion entre
 *     « déclaré » et « mesuré » qui a déjà coûté cher ici ;
 *  2. **laisser éprouver la voix** avant de s'en servir en mission — une
 *     synthèse qu'on n'a jamais entendue n'est pas un réglage, c'est un
 *     pari ;
 *  3. **régler**, et rendre les bornes visibles.
 */

/* Les deux formes viennent du client et ne sont plus recopiees ici.
   Cette copie locale avait la meme forme au caractere pres, et c'est
   precisement ce qui casse : ajouter `moteur` cote client laissait le
   Center sur l'ancienne definition, avec huit erreurs de typage pour un
   seul champ. Une forme, une declaration. */
type Capacite = VoiceCapability;
type Preferences = VoicePreferences;

const DEFAUTS: Preferences = {
  langue: "fr-FR", voix: "", debit: 1, hauteur: 1,
  lecture_automatique: false, mains_libres: false,
  // Les modèles locaux par défaut : ils sont installés, ils rendent mieux
  // qu'une voix système, et ils tournent sur CPU — donc sans rien coûter
  // au modèle qui porte les missions.
  moteur: "serveur",
};

export function VoiceCenter() {
  const [prefs, setPrefs] = useState<Preferences>(DEFAUTS);
  const [capacites, setCapacites] = useState<Capacite[]>([]);
  const [chargement, setChargement] = useState(true);
  const [enregistre, setEnregistre] = useState<"" | "en cours" | "fait">("");

  useEffect(() => {
    let vivant = true;
    voiceClient
      .state()
      .then((d) => {
        if (!vivant) return;
        setPrefs({ ...DEFAUTS, ...(d.preferences ?? {}) });
        setCapacites(d.capacites ?? []);
      })
      .catch(() => { /* réglages locaux : l'écran reste utilisable */ })
      .finally(() => vivant && setChargement(false));
    return () => { vivant = false; };
  }, []);

  // L'enregistrement est différé : bouger un curseur ne doit pas produire
  // une requête par pixel.
  const minuteur = useRef<ReturnType<typeof setTimeout> | null>(null);
  const majPrefs = useCallback((patch: Partial<Preferences>) => {
    setPrefs((p) => {
      const suivant = { ...p, ...patch };
      if (minuteur.current) clearTimeout(minuteur.current);
      setEnregistre("en cours");
      minuteur.current = setTimeout(() => {
        voiceClient
          .savePreferences(suivant)
          // Le serveur borne les valeurs : on reprend les siennes, sinon
          // l'écran afficherait un débit de 9 que personne n'a retenu.
          .then((d) => d?.preferences && setPrefs({ ...DEFAUTS, ...d.preferences }))
          .then(() => setEnregistre("fait"))
          .catch(() => setEnregistre(""));
      }, 400);
      return suivant;
    });
  }, []);

  const dictee = useDictee(prefs.langue, undefined, prefs.moteur);
  const synthese = useSynthese(prefs.voix, prefs.debit, prefs.hauteur, prefs.moteur);

  // Les deux postures vocales de l'operateur (HOS-182). Elles n'ont aucun
  // topic correspondant sur le bus — la dictee et la synthese vivent
  // entierement dans le navigateur — et sont donc declarees ici, la ou l'on
  // sait. La tenue est longue et renouvelee tant que l'etat dure : ni la
  // dictee ni la synthese n'emettent de battement.
  const signalerOperateur = useCockpitStore((s) => s.signalerOperateur);
  const tairelOperateur = useCockpitStore((s) => s.tairelOperateur);
  useEffect(() => {
    if (dictee.ecoute) signalerOperateur("ecoute", "micro ouvert", 3600_000);
    else if (synthese.parle) signalerOperateur("parole", "synthese en cours", 3600_000);
    else tairelOperateur();
    return () => tairelOperateur();
  }, [dictee.ecoute, synthese.parle, signalerOperateur, tairelOperateur]);
  const voixListe = useVoixFiltrees(synthese.voix, prefs.langue);

  const transcription = useMemo(
    () => [dictee.texte, dictee.provisoire].filter(Boolean).join(" "),
    [dictee.texte, dictee.provisoire],
  );

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Voice Center"
        subtitle="Dictée, synthèse et mains libres — ce que la machine sait vraiment faire"
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1.15fr_1fr] gap-6">
        <div className="flex flex-col gap-6">
          <Dictaphone
            dictee={dictee}
            transcription={transcription}
            surEnvoi={() => { /* branché sur l'Assistant en aval */ }}
          />
          <Essai synthese={synthese} langue={prefs.langue} />
        </div>

        <div className="flex flex-col gap-6">
          <Reglages
            prefs={prefs}
            voix={voixListe}
            syntheseDispo={synthese.disponible}
            enregistre={enregistre}
            onChange={majPrefs}
          />
          <Capacites capacites={capacites} chargement={chargement} />
        </div>
      </div>
    </div>
  );
}

/* ── Dictée ─────────────────────────────────────────────────────────── */

function Dictaphone({
  dictee, transcription, surEnvoi,
}: {
  dictee: ReturnType<typeof useDictee>;
  transcription: string;
  surEnvoi: () => void;
}) {
  if (!dictee.disponible) {
    return (
      <Card title="Dictée" subtitle="Reconnaissance vocale du navigateur">
        <Absent
          quoi="La reconnaissance vocale"
          pourquoi="Ce navigateur ne l'expose pas. Chrome et Edge la fournissent ; Firefox ne l'implémente pas."
        />
      </Card>
    );
  }

  return (
    <Card
      title="Dictée"
      subtitle="Reconnaissance du navigateur — aucun modèle local, aucune VRAM"
    >
      <div className="flex items-start gap-4">
        <button
          type="button"
          onClick={dictee.ecoute ? dictee.arreter : dictee.demarrer}
          aria-label={dictee.ecoute ? "Arrêter la dictée" : "Démarrer la dictée"}
          className={`relative shrink-0 h-16 w-16 rounded-full border grid place-items-center transition-colors ${
            dictee.ecoute
              ? "border-hermes-sodium bg-hermes-sodium/10 text-hermes-sodium"
              : "border-hermes-border bg-hermes-bg text-hermes-muted hover:border-hermes-border-bright hover:text-hermes-text"
          }`}
        >
          {dictee.ecoute && (
            <span className="absolute inset-0 rounded-full border border-hermes-sodium/40 animate-ping" />
          )}
          {dictee.ecoute ? <Mic size={22} /> : <MicOff size={22} />}
        </button>

        <div className="min-w-0 flex-1">
          <div className="tech-label text-hermes-dim mb-1.5">
            {dictee.transcrit
              ? "transcription…"
              : dictee.ecoute
                ? (dictee.moteurEffectif === "serveur" ? "enregistrement" : "à l'écoute")
                : "au repos"}
          </div>
          <div
            className="min-h-[5.5rem] rounded-lg border border-hermes-border bg-hermes-bg px-3.5 py-3 text-sm leading-relaxed text-hermes-text"
            aria-live="polite"
          >
            {transcription ? (
              <>
                <span>{dictee.texte}</span>{" "}
                <span className="text-hermes-muted italic">{dictee.provisoire}</span>
              </>
            ) : (
              <span className="text-hermes-dim">
                Parlez : le texte confirmé apparaît en clair, ce qui est encore
                en cours d'audition en gris.
              </span>
            )}
          </div>

          {dictee.erreur && (
            <p className="mt-2 text-xs text-hermes-alarm">{dictee.erreur}</p>
          )}

          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={surEnvoi}
              disabled={!dictee.texte}
              className="inline-flex items-center gap-1.5 rounded-md border border-hermes-border bg-hermes-elevated px-3 py-1.5 text-xs text-hermes-text disabled:opacity-40 hover:border-hermes-sodium/60"
            >
              <Send size={13} /> Envoyer à l'Assistant
            </button>
            <button
              type="button"
              onClick={dictee.vider}
              disabled={!transcription}
              className="rounded-md border border-hermes-border px-3 py-1.5 text-xs text-hermes-muted disabled:opacity-40 hover:text-hermes-text"
            >
              Effacer
            </button>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ── Essai de synthèse ──────────────────────────────────────────────── */

const PHRASE = "Mission lancée. Trois sections vérifiées, une signalée.";

function Essai({
  synthese, langue,
}: {
  synthese: ReturnType<typeof useSynthese>;
  langue: string;
}) {
  const [phrase, setPhrase] = useState(PHRASE);

  if (!synthese.disponible) {
    return (
      <Card title="Synthèse" subtitle="Lecture des réponses">
        <Absent
          quoi="La synthèse vocale"
          pourquoi="Ni voix locale sur le serveur, ni speechSynthesis dans ce navigateur."
        />
      </Card>
    );
  }

  return (
    <Card
      title="Synthèse"
      subtitle="Éprouvez la voix avant de la confier à une mission"
    >
      <textarea
        value={phrase}
        onChange={(e) => setPhrase(e.target.value)}
        rows={2}
        lang={langue}
        className="w-full resize-none rounded-lg border border-hermes-border bg-hermes-bg px-3.5 py-2.5 text-sm text-hermes-text outline-none focus:border-hermes-sodium"
      />
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => synthese.dire(phrase)}
          className="inline-flex items-center gap-1.5 rounded-md border border-hermes-sodium/50 bg-hermes-sodium/10 px-3 py-1.5 text-xs text-hermes-sodium hover:bg-hermes-sodium/15"
        >
          <Volume2 size={13} /> Écouter
        </button>
        <button
          type="button"
          onClick={synthese.taire}
          disabled={!synthese.parle}
          className="inline-flex items-center gap-1.5 rounded-md border border-hermes-border px-3 py-1.5 text-xs text-hermes-muted disabled:opacity-40 hover:text-hermes-text"
        >
          <VolumeX size={13} /> Couper
        </button>
        {synthese.parle && (
          <span className="inline-flex items-center gap-1.5 text-xs text-hermes-arc">
            <Radio size={12} className="animate-pulse" /> en cours
          </span>
        )}
        <span className="tech-label ml-auto !text-[8.5px]">
          {synthese.moteurEffectif === "serveur" ? "PIPER LOCAL" : "NAVIGATEUR"}
        </span>
      </div>

      {/* Un repli silencieux ferait croire que la voix locale a parlé. */}
      {synthese.repli && (
        <p className="mt-2 text-[11px] text-hermes-amber">{synthese.repli}</p>
      )}
    </Card>
  );
}

/* ── Réglages ───────────────────────────────────────────────────────── */

function Reglages({
  prefs, voix, syntheseDispo, enregistre, onChange,
}: {
  prefs: Preferences;
  voix: { nom: string; langue: string; locale: boolean }[];
  syntheseDispo: boolean;
  enregistre: "" | "en cours" | "fait";
  onChange: (p: Partial<Preferences>) => void;
}) {
  return (
    <Card
      title="Réglages"
      subtitle="Conservés côté serveur, bornés à ce que l'API accepte"
      action={
        enregistre === "en cours" ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-hermes-muted">
            <Loader2 size={11} className="animate-spin" /> enregistrement
          </span>
        ) : enregistre === "fait" ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-hermes-arc">
            <Check size={11} /> enregistré
          </span>
        ) : null
      }
    >
      <div className="flex flex-col gap-4">
        <Champ label="Moteur">
          <div className="grid grid-cols-2 gap-2">
            {([
              ["serveur", "Modèles locaux", "Piper + faster-whisper, sur CPU"],
              ["navigateur", "Navigateur", "API Web Speech de Chrome"],
            ] as const).map(([id, titre, detail]) => (
              <button
                key={id}
                type="button"
                onClick={() => onChange({ moteur: id })}
                aria-pressed={prefs.moteur === id}
                className={`clip-corner-sm border px-3 py-2 text-left transition-colors ${
                  prefs.moteur === id
                    ? "border-hermes-sodium/60 bg-hermes-sodium/10"
                    : "border-hermes-border hover:border-hermes-border-bright"
                }`}
              >
                <span className={`block text-xs ${prefs.moteur === id ? "text-hermes-sodium" : "text-hermes-text"}`}>
                  {titre}
                </span>
                <span className="tech-label mt-1 block !text-[8.5px] normal-case tracking-normal">
                  {detail}
                </span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-hermes-dim">
            Le navigateur reste le repli automatique : si le serveur ne répond
            pas, la voix système prend le relais et l&apos;écran le dit plutôt
            que de laisser croire que Piper a parlé.
          </p>
        </Champ>

        <Champ label="Langue de dictée">
          <select
            value={prefs.langue}
            onChange={(e) => onChange({ langue: e.target.value })}
            className="w-full rounded-md border border-hermes-border bg-hermes-bg px-2.5 py-1.5 text-sm text-hermes-text outline-none focus:border-hermes-sodium"
          >
            {LANGUES.map((l) => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
        </Champ>

        <Champ label="Voix">
          {!syntheseDispo ? (
            <p className="text-xs text-hermes-dim">Synthèse indisponible ici.</p>
          ) : voix.length === 0 ? (
            <p className="text-xs text-hermes-dim">
              Aucune voix installée sur ce système.
            </p>
          ) : (
            <select
              value={prefs.voix}
              onChange={(e) => onChange({ voix: e.target.value })}
              className="w-full rounded-md border border-hermes-border bg-hermes-bg px-2.5 py-1.5 text-sm text-hermes-text outline-none focus:border-hermes-sodium"
            >
              <option value="">Voix par défaut du système</option>
              {voix.map((v) => (
                <option key={v.nom} value={v.nom}>
                  {v.nom} — {v.langue}{v.locale ? "" : " (réseau)"}
                </option>
              ))}
            </select>
          )}
        </Champ>

        <Curseur
          label="Débit" valeur={prefs.debit}
          onChange={(v) => onChange({ debit: v })}
        />
        <Curseur
          label="Hauteur" valeur={prefs.hauteur}
          onChange={(v) => onChange({ hauteur: v })}
        />

        <Bascule
          label="Lire les réponses à voix haute"
          aide="L'Assistant reste muet tant que ceci est décoché."
          actif={prefs.lecture_automatique}
          onChange={(v) => onChange({ lecture_automatique: v })}
        />
        <Bascule
          label="Mains libres"
          aide="Envoie la dictée dès qu'un silence est détecté, sans clic."
          actif={prefs.mains_libres}
          onChange={(v) => onChange({ mains_libres: v })}
        />
      </div>
    </Card>
  );
}

function Champ({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="tech-label text-hermes-dim">{label}</span>
      {children}
    </label>
  );
}

function Curseur({
  label, valeur, onChange,
}: { label: string; valeur: number; onChange: (v: number) => void }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="tech-label text-hermes-dim flex items-center justify-between">
        {label}
        <span className="tabular-nums text-hermes-muted">{valeur.toFixed(2)}×</span>
      </span>
      <input
        type="range" min={0.5} max={2} step={0.05} value={valeur}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--hermes-sodium)]"
      />
    </label>
  );
}

function Bascule({
  label, aide, actif, onChange,
}: { label: string; aide: string; actif: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={actif}
      onClick={() => onChange(!actif)}
      className="flex items-start gap-3 text-left"
    >
      <span
        className={`mt-0.5 h-5 w-9 shrink-0 rounded-full border transition-colors ${
          actif
            ? "border-hermes-sodium bg-hermes-sodium/25"
            : "border-hermes-border bg-hermes-bg"
        }`}
      >
        <span
          className={`block h-3.5 w-3.5 rounded-full transition-transform ${
            actif ? "translate-x-[1.15rem] bg-hermes-sodium" : "translate-x-[3px] bg-hermes-dim"
          } mt-[3px]`}
        />
      </span>
      <span className="min-w-0">
        <span className="block text-sm text-hermes-text">{label}</span>
        <span className="block text-xs text-hermes-dim">{aide}</span>
      </span>
    </button>
  );
}

/* ── Capacités ──────────────────────────────────────────────────────── */

function Capacites({
  capacites, chargement,
}: { capacites: Capacite[]; chargement: boolean }) {
  return (
    <Card
      title="Ce qui est réellement disponible"
      subtitle="Fournisseurs interrogés, pas déclarés"
    >
      {chargement ? (
        <p className="text-xs text-hermes-dim">Interrogation…</p>
      ) : capacites.length === 0 ? (
        <p className="text-xs text-hermes-dim">Backend injoignable.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-hermes-border">
          {capacites.map((c) => (
            <li key={`${c.ou}-${c.genre}`} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
              <span className="mt-0.5">
                {c.disponible
                  ? <Check size={14} className="text-hermes-arc" />
                  : <X size={14} className="text-hermes-dim" />}
              </span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-hermes-text">{c.nom}</span>
                  <Badge variant={c.ou === "navigateur" ? "info" : "default"}>
                    {c.ou}
                  </Badge>
                </div>
                <p className="text-xs text-hermes-dim leading-relaxed">{c.detail}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Absent({ quoi, pourquoi }: { quoi: string; pourquoi: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-hermes-border bg-hermes-bg px-3.5 py-3">
      <X size={15} className="mt-0.5 shrink-0 text-hermes-dim" />
      <p className="text-sm text-hermes-muted leading-relaxed">
        <span className="text-hermes-text">{quoi}</span> n'est pas disponible.{" "}
        {pourquoi}
      </p>
    </div>
  );
}

export default VoiceCenter;
