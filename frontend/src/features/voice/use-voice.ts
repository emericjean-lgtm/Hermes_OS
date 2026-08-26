"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

/**
 * La voix, côté navigateur (HOS-173).
 *
 * Chrome et Edge livrent une reconnaissance et une synthèse qui marchent,
 * gratuitement et sans toucher au GPU. Sur cette machine — 16 Gio de VRAM
 * partagés avec le modèle qui porte les missions — c'est décisif : un
 * Whisper local disputerait sa place au cerveau des missions, et le projet
 * a déjà mesuré ce que coûte un second modèle qui réclame la sienne.
 *
 * Ce module n'expose donc que ce que le navigateur sait faire, et il le dit
 * quand il ne sait pas. Aucun contrôle ne s'affiche pour une capacité
 * absente : la règle d'honnêteté appliquée partout ailleurs dans ce
 * Cockpit vaut ici aussi.
 */

interface ResultatBrut {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
  resultIndex: number;
}

interface ReconnaissanceMinimale extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: ResultatBrut) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

type Constructeur = new () => ReconnaissanceMinimale;

function constructeur(): Constructeur | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: Constructeur;
    webkitSpeechRecognition?: Constructeur;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** Les messages d'erreur de l'API sont des codes ; ceci les rend lisibles. */
const MOTIFS: Record<string, string> = {
  "not-allowed": "Micro refusé — autorisez-le dans les réglages du site.",
  "service-not-allowed": "Micro refusé par le système.",
  "no-speech": "Rien entendu.",
  "audio-capture": "Aucun micro détecté.",
  network: "La reconnaissance a besoin du réseau.",
  aborted: "",
};

export interface EtatDictee {
  /** Le navigateur sait-il reconnaître la parole ? */
  disponible: boolean;
  ecoute: boolean;
  /** Ce qui est confirmé, et ce qui est encore en cours d'audition. */
  texte: string;
  provisoire: string;
  erreur: string;
  demarrer: () => void;
  arreter: () => void;
  vider: () => void;
}

export function useDictee(langue: string, surPhrase?: (t: string) => void): EtatDictee {
  const [disponible, setDisponible] = useState(false);
  const [ecoute, setEcoute] = useState(false);
  const [texte, setTexte] = useState("");
  const [provisoire, setProvisoire] = useState("");
  const [erreur, setErreur] = useState("");
  const moteur = useRef<ReconnaissanceMinimale | null>(null);

  // `surPhrase` change à chaque rendu du parent ; le garder dans une ref
  // évite de reconstruire le moteur — ce qui couperait le micro en plein
  // milieu d'une phrase.
  const rappel = useRef(surPhrase);
  rappel.current = surPhrase;

  useEffect(() => {
    setDisponible(constructeur() !== null);
  }, []);

  const demarrer = useCallback(() => {
    const Ctor = constructeur();
    if (!Ctor) return;
    setErreur("");
    const m = new Ctor();
    m.lang = langue;
    m.interimResults = true;
    m.continuous = true;
    m.onstart = () => setEcoute(true);
    m.onresult = (e) => {
      let confirme = "";
      let encours = "";
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        const r = e.results[i];
        const mot = r[0]?.transcript ?? "";
        if (r.isFinal) confirme += mot;
        else encours += mot;
      }
      setProvisoire(encours);
      if (confirme) {
        setTexte((t) => (t ? `${t} ${confirme}` : confirme).trim());
        rappel.current?.(confirme.trim());
      }
    };
    m.onerror = (e) => {
      const motif = MOTIFS[e.error] ?? `Erreur : ${e.error}`;
      if (motif) setErreur(motif);
    };
    m.onend = () => {
      setEcoute(false);
      setProvisoire("");
    };
    moteur.current = m;
    try {
      m.start();
    } catch {
      // `start()` sur un moteur déjà démarré lève ; l'état est déjà bon.
      setEcoute(true);
    }
  }, [langue]);

  const arreter = useCallback(() => {
    moteur.current?.stop();
    moteur.current = null;
  }, []);

  useEffect(() => () => moteur.current?.abort(), []);

  return {
    disponible, ecoute, texte, provisoire, erreur,
    demarrer, arreter,
    vider: () => { setTexte(""); setProvisoire(""); },
  };
}

export interface Voix {
  nom: string;
  langue: string;
  locale: boolean;
}

export interface EtatSynthese {
  disponible: boolean;
  parle: boolean;
  voix: Voix[];
  dire: (texte: string) => void;
  taire: () => void;
}

export function useSynthese(nomVoix: string, debit: number, hauteur: number): EtatSynthese {
  const [voix, setVoix] = useState<Voix[]>([]);
  const [parle, setParle] = useState(false);
  const disponible = typeof window !== "undefined" && "speechSynthesis" in window;

  useEffect(() => {
    if (!disponible) return;
    // Chrome peuple la liste de façon asynchrone : un seul appel au montage
    // rend souvent un tableau vide, et l'écran afficherait « aucune voix »
    // sur une machine qui en a douze.
    const charger = () => {
      setVoix(
        window.speechSynthesis.getVoices().map((v) => ({
          nom: v.name, langue: v.lang, locale: v.localService,
        })),
      );
    };
    charger();
    window.speechSynthesis.addEventListener("voiceschanged", charger);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", charger);
  }, [disponible]);

  const dire = useCallback((texte: string) => {
    if (!disponible || !texte.trim()) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(texte);
    const choisie = window.speechSynthesis.getVoices().find((v) => v.name === nomVoix);
    if (choisie) u.voice = choisie;
    u.rate = debit;
    u.pitch = hauteur;
    u.onstart = () => setParle(true);
    u.onend = () => setParle(false);
    u.onerror = () => setParle(false);
    window.speechSynthesis.speak(u);
  }, [disponible, nomVoix, debit, hauteur]);

  const taire = useCallback(() => {
    if (!disponible) return;
    window.speechSynthesis.cancel();
    setParle(false);
  }, [disponible]);

  return { disponible, parle, voix, dire, taire };
}

/** Les langues que la dictée accepte, du plus probable au moins. */
export const LANGUES = [
  { code: "fr-FR", label: "Français" },
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "es-ES", label: "Español" },
  { code: "de-DE", label: "Deutsch" },
  { code: "it-IT", label: "Italiano" },
] as const;

export function useVoixFiltrees(voix: Voix[], langue: string): Voix[] {
  return useMemo(() => {
    const prefixe = langue.slice(0, 2).toLowerCase();
    const memeLangue = voix.filter((v) => v.langue.toLowerCase().startsWith(prefixe));
    // Les voix d'une autre langue restent listées après : un opérateur
    // francophone peut vouloir une voix anglaise pour lire du code.
    return [...memeLangue, ...voix.filter((v) => !memeLangue.includes(v))];
  }, [voix, langue]);
}
