"use client";

import { useState } from "react";
import { AlertTriangle, Boxes, Film, Layers, Wifi, WifiOff } from "lucide-react";
import { CenterHeader, CenterTabs } from "@/components/center-scaffold";
import { Card } from "@/components/ui/card";
import { useStudioModels, useStudioState, useStudioVram } from "@/hooks/use-api";
import { formatGio, formatGioPair } from "@/lib/format";

/**
 * Studio Center (HOS-190).
 *
 * La surface d'opération de la génération d'images et de plans vidéo. Elle
 * ne compose pas de graphe : c'est le travail de Hermes Agent, par ses
 * outils `studio_*`. Ce que cet écran apporte, c'est ce que ni ComfyUI ni
 * l'agent ne voient — **l'état de la carte, partagée**.
 *
 * ## Pourquoi la VRAM est en tête et pas en bas
 *
 * Les 16 Gio de la RX 6800 sont indivisibles. Ollama tenant gpt-oss occupe
 * 13,21 Gio ; LTX-2.5 en Q3_K_M en réclame 10,73. Ils ne peuvent pas
 * coexister, et rien ne le dit : ROCm complète en mémoire système sans
 * lever d'erreur. Mesuré le 2026-08-27 — 3 226 ms contre 187 ms pour un
 * résultat identique.
 *
 * Un rendu qui déborde **aboutit**. C'est tout le problème : il aboutit
 * dix-sept fois plus lentement, et la lenteur se lit comme « ce modèle est
 * mauvais » plutôt que « la mémoire a débordé ». D'où le bandeau.
 *
 * ## L'onglet Graphe
 *
 * L'interface de ComfyUI, en cadre. ComfyUI ne pose ni `X-Frame-Options`
 * ni `frame-ancestors` : l'encastrement fonctionne. C'est l'atelier pour
 * bricoler un graphe à la main — pas la surface principale, qui serait
 * alors du changement d'application sans le changement de fenêtre.
 */

type Onglet = "atelier" | "graphe";

const COMFY_URL = "http://127.0.0.1:8188";

export function StudioCenter() {
  const [onglet, setOnglet] = useState<Onglet>("atelier");
  const { data: etat } = useStudioState();
  const { data: modeles } = useStudioModels();

  const rendActif = (etat?.file.en_cours ?? 0) > 0;
  const { data: vram } = useStudioVram(rendActif);

  return (
    <div className="animate-fade-in">
      <CenterHeader
        title="Studio Center"
        subtitle="Génération d'images et de plans vidéo, sur la carte partagée"
        right={
          <CenterTabs<Onglet>
            tabs={[
              { id: "atelier", label: "Atelier" },
              { id: "graphe", label: "Graphe" },
            ]}
            active={onglet}
            onChange={setOnglet}
          />
        }
      />

      {onglet === "atelier" ? (
        <Atelier etat={etat} modeles={modeles} vram={vram} rendActif={rendActif} />
      ) : (
        <Graphe joignable={etat?.joignable ?? false} />
      )}
    </div>
  );
}

/* ── Atelier ─────────────────────────────────────────────────────────── */

function Atelier({
  etat, modeles, vram, rendActif,
}: {
  etat?: ReturnType<typeof useStudioState>["data"];
  modeles?: ReturnType<typeof useStudioModels>["data"];
  vram?: ReturnType<typeof useStudioVram>["data"];
  rendActif: boolean;
}) {
  if (!etat) {
    return <p className="text-xs text-hermes-dim">Relevé en cours…</p>;
  }

  if (!etat.joignable) {
    return (
      <Card title="Runtime de génération" subtitle="ComfyUI">
        <div className="flex items-start gap-3">
          <WifiOff size={16} className="mt-0.5 shrink-0 text-hermes-red" />
          <div>
            <p className="text-sm text-hermes-text">ComfyUI ne répond pas.</p>
            <p className="mt-1.5 max-w-[80ch] text-[11.5px] leading-relaxed text-hermes-muted">
              Rien ne peut être généré tant qu&apos;il n&apos;est pas démarré.
              Le lanceur qui porte les bons réglages est{" "}
              <span className="num text-hermes-text">hermes-ltx.bat</span>, dans
              le dossier de ComfyUI — il fixe l&apos;attention sub-quadratique et
              la sortie sur E:.
            </p>
            {etat.detail && (
              <p className="num mt-2 text-[10px] text-hermes-dim">{etat.detail}</p>
            )}
          </div>
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Le seul réglage qui décide du débordement, et il se lit. */}
      {!etat.attention_sub_quadratique && (
        <div className="clip-corner flex items-start gap-4 border border-hermes-amber/40
          bg-hermes-surface/60 p-4">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-hermes-amber" />
          <div>
            <div className="tech-label mb-1.5 !text-hermes-amber">
              Attention par défaut — les rendus déborderont
            </div>
            <p className="max-w-[100ch] text-[12px] leading-relaxed text-hermes-muted">
              ComfyUI tourne sans{" "}
              <span className="num text-hermes-text">--use-quad-cross-attention</span>.
              Sur cette carte, `gfx1030` n&apos;a ni Flash ni Memory-Efficient SDP :
              l&apos;attention par défaut matérialise la matrice entière et réclame
              <span className="num text-hermes-text"> 20,16 Gio</span> à 16 384 jetons,
              sur une carte de 15,98. Le rendu <em>aboutira</em> — en{" "}
              <span className="num text-hermes-text">3 226 ms</span> au lieu de{" "}
              <span className="num text-hermes-text">187</span>, la mémoire système
              prenant le relais sans qu&apos;aucune erreur ne le dise.
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card
          title="Carte"
          subtitle="Ce que le processus de rendu détient vraiment"
        >
          <Vram etat={etat} vram={vram} rendActif={rendActif} />
        </Card>

        <Card title="File" subtitle="Rendus en cours et en attente">
          <div className="flex items-baseline gap-6">
            <Chiffre valeur={etat.file.en_cours} label="En cours"
                     teinte={rendActif ? "var(--hermes-sodium)" : undefined} />
            <Chiffre valeur={etat.file.en_attente} label="En attente" />
          </div>
          <p className="mt-3 text-[11px] leading-relaxed text-hermes-dim">
            Un seul locataire lourd à la fois. Un rendu demandé pendant
            qu&apos;une mission tient la carte est refusé plutôt que lancé —
            un rendu qui déborde aboutit, et c&apos;est précisément ce
            qu&apos;on veut éviter.
          </p>
        </Card>

        <Card title="Runtime" subtitle={`ComfyUI ${etat.version || "—"}`}>
          <div className="flex items-center gap-2 text-sm text-hermes-arc">
            <Wifi size={14} /> joignable
          </div>
          <div className="mt-3 flex flex-col gap-1.5">
            <Ligne libelle="Attention"
                   valeur={etat.attention_sub_quadratique ? "sub-quadratique" : "par défaut"}
                   alerte={!etat.attention_sub_quadratique} />
            <Ligne libelle="VRAM totale" valeur={`${formatGio(etat.vram_totale)} Gio`} />
          </div>
        </Card>
      </div>

      <Card
        title="Modèles chargeables"
        subtitle="Ce que les chargeurs voient sur le disque, et rien d'autre"
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Famille icone={<Layers size={12} />} nom="Diffusion"
                   fichiers={modeles?.diffusion} />
          <Famille icone={<Boxes size={12} />} nom="Encodeurs de texte"
                   fichiers={modeles?.encodeurs} />
          <Famille icone={<Film size={12} />} nom="VAE"
                   fichiers={modeles?.vae} />
        </div>
      </Card>
    </div>
  );
}

/* ── Morceaux ────────────────────────────────────────────────────────── */

function Vram({
  etat, vram, rendActif,
}: {
  etat: NonNullable<ReturnType<typeof useStudioState>["data"]>;
  vram?: ReturnType<typeof useStudioVram>["data"];
  rendActif: boolean;
}) {
  const total = etat.vram_totale || 1;
  // `mesure: false` n'est pas zéro. Écrire « 0 Gio » ferait lire « rien ne
  // tourne » là où il faut lire « je n'ai pas pu mesurer ».
  const mesure = vram?.mesure === true && typeof vram.octets === "number";
  const pris = mesure ? (vram!.octets as number) : 0;
  const pct = Math.min(100, Math.round((pris / total) * 100));
  const deborde = mesure && pris > total * 0.985;

  return (
    <>
      {mesure ? (
        <>
          <div className="flex items-baseline gap-1.5">
            <span className="num text-2xl"
                  style={{ color: deborde ? "var(--hermes-red)" : "var(--hermes-sodium)" }}>
              {formatGioPair(pris, total)}
            </span>
          </div>
          <div className="mt-2.5 h-1 w-full overflow-hidden bg-hermes-border">
            <div className="h-full transition-[width] duration-500"
                 style={{
                   width: `${pct}%`,
                   background: deborde ? "var(--hermes-red)" : "var(--hermes-sodium)",
                 }} />
          </div>
          {deborde && (
            <p className="mt-2 text-[11px] leading-relaxed text-hermes-red">
              Au-delà de 98,5 %, ROCm complète en mémoire système sans lever
              d&apos;erreur. Ce rendu aboutira, dix-sept fois plus lentement.
            </p>
          )}
        </>
      ) : (
        <>
          <span className="num text-2xl text-hermes-dim">non mesuré</span>
          <p className="mt-2 text-[11px] leading-relaxed text-hermes-dim">
            {vram?.raison ?? "Le compteur GPU n'a rien rendu."} Ce n&apos;est
            pas « zéro octet » : la mesure n&apos;a pas eu lieu.
          </p>
        </>
      )}
      {rendActif && mesure && (
        <p className="tech-label mt-2">Relevé toutes les 2 s pendant le rendu</p>
      )}
    </>
  );
}

function Chiffre({ valeur, label, teinte }: {
  valeur: number; label: string; teinte?: string;
}) {
  return (
    <div>
      <div className="num text-2xl" style={{ color: teinte ?? "var(--hermes-text)" }}>
        {valeur}
      </div>
      <div className="tech-label mt-1">{label}</div>
    </div>
  );
}

function Ligne({ libelle, valeur, alerte }: {
  libelle: string; valeur: string; alerte?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="tech-label">{libelle}</span>
      <span className={`num text-[11px] ${alerte ? "text-hermes-amber" : "text-hermes-text"}`}>
        {valeur}
      </span>
    </div>
  );
}

function Famille({ icone, nom, fichiers }: {
  icone: React.ReactNode; nom: string; fichiers?: string[];
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5">
        <span className="text-hermes-sodium">{icone}</span>
        <span className="tech-label !text-hermes-sodium">{nom}</span>
        <span className="num text-[10px] text-hermes-dim">{fichiers?.length ?? 0}</span>
      </div>
      {!fichiers?.length ? (
        <p className="text-[11px] text-hermes-dim">
          Aucun fichier — rien ne peut être chargé.
        </p>
      ) : (
        <div className="flex flex-col gap-1">
          {fichiers.map((f) => (
            <span key={f} className="num truncate text-[10px] text-hermes-muted" title={f}>
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Graphe ──────────────────────────────────────────────────────────── */

function Graphe({ joignable }: { joignable: boolean }) {
  if (!joignable) {
    return (
      <Card title="Éditeur de graphe" subtitle="ComfyUI">
        <p className="text-sm text-hermes-muted">
          ComfyUI ne répond pas — il n&apos;y a rien à encadrer.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11.5px] leading-relaxed text-hermes-muted">
        L&apos;éditeur de ComfyUI, tel quel. C&apos;est l&apos;atelier pour
        bricoler un graphe à la main ; la production passe par l&apos;agent,
        qui appelle les outils <span className="num text-hermes-text">studio_*</span>{" "}
        et bénéficie de l&apos;arbitrage de la carte — ce que cet éditeur, lui,
        ignore.
      </p>
      <div className="clip-corner overflow-hidden border border-hermes-border"
           style={{ height: "calc(100vh - var(--bar-h) - var(--foot-h) - 190px)" }}>
        <iframe
          src={COMFY_URL}
          title="ComfyUI"
          className="h-full w-full border-0 bg-white"
        />
      </div>
    </div>
  );
}

export default StudioCenter;
