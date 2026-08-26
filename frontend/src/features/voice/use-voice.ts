"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { voiceClient } from "@/services/client";

/** Qui parle et qui ecoute. `serveur` = Piper et faster-whisper, qui
 *  tournent sur CPU et ne disputent rien a la VRAM du modele de mission ;
 *  `navigateur` = les API Web Speech, gardees en repli. */
export type MoteurVocal = "serveur" | "navigateur";

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
  /** La dictée est-elle possible — par le moteur retenu ou par son repli. */
  disponible: boolean;
  ecoute: boolean;
  /** Ce qui est confirmé, et ce qui est encore en cours d'audition.
   *
   *  `provisoire` reste vide en mode serveur, et ce n'est pas un oubli :
   *  faster-whisper transcrit un fichier, pas un flux. Le texte arrive
   *  d'un coup à l'arrêt. Prétendre le contraire par une animation serait
   *  inventer une audition en direct qui n'a pas lieu. */
  texte: string;
  provisoire: string;
  erreur: string;
  /** Le serveur transcrit en ce moment — après l'arrêt, avant le texte. */
  transcrit: boolean;
  /** Quel moteur a réellement servi. Diffère du réglage quand le premier
   *  a échoué : l'écran doit pouvoir le dire au lieu de laisser croire. */
  moteurEffectif: MoteurVocal;
  demarrer: () => void;
  arreter: () => void;
  vider: () => void;
}

export function useDictee(
  langue: string,
  surPhrase?: (t: string) => void,
  moteurVoulu: MoteurVocal = "serveur",
): EtatDictee {
  const [disponible, setDisponible] = useState(false);
  const [ecoute, setEcoute] = useState(false);
  const [texte, setTexte] = useState("");
  const [provisoire, setProvisoire] = useState("");
  const [erreur, setErreur] = useState("");
  const [transcrit, setTranscrit] = useState(false);
  const [moteurEffectif, setMoteurEffectif] = useState<MoteurVocal>(moteurVoulu);
  const moteur = useRef<ReconnaissanceMinimale | null>(null);
  const enregistreur = useRef<MediaRecorder | null>(null);
  const morceaux = useRef<Blob[]>([]);
  const flux = useRef<MediaStream | null>(null);

  // `surPhrase` change à chaque rendu du parent ; le garder dans une ref
  // évite de reconstruire le moteur — ce qui couperait le micro en plein
  // milieu d'une phrase.
  const rappel = useRef(surPhrase);
  rappel.current = surPhrase;

  useEffect(() => {
    setDisponible(constructeur() !== null);
  }, []);

  /** Couper le micro et rendre le peripherique.
   *
   *  Les pistes doivent etre arretees explicitement : sans cela le voyant
   *  d'enregistrement du navigateur reste allume apres la dictee, ce qui
   *  laisse croire que l'application ecoute encore. */
  const rendreLeMicro = useCallback(() => {
    flux.current?.getTracks().forEach((p) => p.stop());
    flux.current = null;
  }, []);

  const demarrerServeur = useCallback(async () => {
    setErreur("");
    morceaux.current = [];
    try {
      const f = await navigator.mediaDevices.getUserMedia({ audio: true });
      flux.current = f;
      const e = new MediaRecorder(f);
      e.ondataavailable = (ev) => { if (ev.data.size) morceaux.current.push(ev.data); };
      e.onstop = async () => {
        rendreLeMicro();
        const audio = new Blob(morceaux.current, { type: e.mimeType || "audio/webm" });
        morceaux.current = [];
        // Un enregistrement quasi vide ne vaut pas un aller-retour : le
        // serveur rendrait une chaine vide et l'ecran afficherait un
        // succes sans texte.
        if (audio.size < 1200) { setTranscrit(false); return; }
        setTranscrit(true);
        try {
          const r = await voiceClient.transcribe(audio);
          const t = (r.texte || "").trim();
          if (t) {
            setTexte((x) => (x ? `${x} ${t}` : t).trim());
            rappel.current?.(t);
          } else {
            setErreur("Rien n'a été reconnu dans cet enregistrement.");
          }
        } catch {
          setErreur("Le serveur n'a pas pu transcrire — réglez le moteur sur « navigateur ».");
        } finally {
          setTranscrit(false);
        }
      };
      enregistreur.current = e;
      e.start();
      setMoteurEffectif("serveur");
      setEcoute(true);
      return true;
    } catch {
      // Micro refuse, ou MediaRecorder absent : le navigateur reste une
      // vraie option, et le dire vaut mieux que se taire.
      rendreLeMicro();
      return false;
    }
  }, [rendreLeMicro]);

  const demarrer = useCallback(() => {
    if (moteurVoulu === "serveur") {
      void demarrerServeur().then((ok) => {
        if (!ok) {
          setMoteurEffectif("navigateur");
          demarrerNavigateur();
        }
      });
      return;
    }
    setMoteurEffectif("navigateur");
    demarrerNavigateur();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moteurVoulu, demarrerServeur]);

  const demarrerNavigateur = useCallback(() => {
    const Ctor = constructeur();
    if (!Ctor) {
      setErreur("Ce navigateur ne reconnaît pas la parole, et le serveur non plus.");
      return;
    }
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
    if (enregistreur.current && enregistreur.current.state !== "inactive") {
      enregistreur.current.stop();
      enregistreur.current = null;
      setEcoute(false);
      return;
    }
    moteur.current?.stop();
    moteur.current = null;
  }, []);

  useEffect(() => () => {
    moteur.current?.abort();
    if (enregistreur.current?.state !== "inactive") enregistreur.current?.stop();
    flux.current?.getTracks().forEach((p) => p.stop());
  }, []);

  return {
    // Le serveur transcrit meme quand le navigateur ne reconnait rien :
    // la dictee est donc possible des que l'un des deux repond.
    disponible: disponible || moteurVoulu === "serveur",
    ecoute, texte, provisoire, erreur, transcrit, moteurEffectif,
    demarrer, arreter,
    vider: () => { setTexte(""); setProvisoire(""); setErreur(""); },
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
  /** Quel moteur a réellement parlé. */
  moteurEffectif: MoteurVocal;
  /** Pourquoi le serveur a été abandonné, s'il l'a été. Vide sinon. */
  repli: string;
  dire: (texte: string) => void;
  taire: () => void;
}

export function useSynthese(
  nomVoix: string,
  debit: number,
  hauteur: number,
  moteurVoulu: MoteurVocal = "serveur",
): EtatSynthese {
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

  const audio = useRef<HTMLAudioElement | null>(null);
  const [moteurEffectif, setMoteurEffectif] = useState<MoteurVocal>(moteurVoulu);
  const [repli, setRepli] = useState("");

  const direNavigateur = useCallback((texte: string) => {
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

  /** La voix locale du serveur.
   *
   *  Le nom de voix n'est pas transmis : la preference `voix` designe une
   *  voix *du navigateur*, et l'envoyer a Piper produirait une 4xx sur un
   *  nom qu'il ne connait pas. Le serveur applique la sienne, annoncee par
   *  `/voice/state`.
   *
   *  `debit` et `hauteur` ne s'appliquent pas non plus : Piper ne les
   *  expose pas. Les taire vaut mieux que les envoyer en pure perte, et
   *  l'ecran le dit a cote des curseurs. */
  const direServeur = useCallback(async (texte: string) => {
    const wav = await voiceClient.speak(texte);
    const url = URL.createObjectURL(wav);
    const a = new Audio(url);
    audio.current = a;
    a.onended = () => { setParle(false); URL.revokeObjectURL(url); };
    a.onerror = () => { setParle(false); URL.revokeObjectURL(url); };
    setParle(true);
    await a.play();
  }, []);

  const dire = useCallback((texte: string) => {
    if (!texte.trim()) return;
    if (audio.current) { audio.current.pause(); audio.current = null; }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (moteurVoulu === "serveur") {
      setMoteurEffectif("serveur");
      setRepli("");
      void direServeur(texte).catch(() => {
        // Le serveur n'a pas de voix locale, ou ne repond pas. Une voix
        // systeme imparfaite vaut mieux qu'un silence — mais il faut le
        // dire, sinon l'operateur croit entendre Piper.
        setParle(false);
        setMoteurEffectif("navigateur");
        setRepli("Le serveur n'a pas répondu — voix du navigateur.");
        direNavigateur(texte);
      });
      return;
    }
    setMoteurEffectif("navigateur");
    setRepli("");
    direNavigateur(texte);
  }, [moteurVoulu, direServeur, direNavigateur]);

  const taire = useCallback(() => {
    if (audio.current) { audio.current.pause(); audio.current = null; }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setParle(false);
  }, []);

  return {
    // Le serveur parle meme sans `speechSynthesis` : la synthese est donc
    // possible des que l'un des deux repond.
    disponible: disponible || moteurVoulu === "serveur",
    parle, voix, moteurEffectif, repli, dire, taire,
  };
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
