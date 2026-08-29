"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Dices, Film, Gauge, Image as ImageIcon,
         Loader2, Link2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useStudioCalibration, useStudioCalibrer, useStudioCompose,
         useStudioTemplates } from "@/hooks/use-api";
import type { GabaritDTO } from "@/services/client";

/**
 * Le formulaire de rendu du Studio Center (HOS-194).
 *
 * ## Pourquoi il existe
 *
 * L'onglet Atelier montrait la VRAM, la file et les modèles, et ne
 * permettait de lancer **rien**. Pour produire un plan il fallait passer
 * par l'agent ou par l'éditeur de ComfyUI — c'est-à-dire par une autre
 * application, ce que ce Center devait précisément éviter.
 *
 * ## Ce qu'il ne fait pas
 *
 * Il ne compose pas de graphe. Il envoie un **nom de gabarit** et des
 * paramètres explicites ; le graphe est bâti côté serveur par
 * `backend/studio/gabarits.py`, à partir de valeurs mesurées. Rien n'est
 * inféré de la consigne — ni la durée, ni le format, ni le modèle.
 *
 * La liste des gabarits et des formats vient du backend et n'est pas
 * recopiée ici : deux listes du même fait finissent par diverger.
 */

/** Les champs numériques, hors durée — celle-ci a sa propre commande
 *  parce qu'elle ne s'envoie pas telle quelle (voir `Duree` plus bas).
 *
 *  `images` n'y figure plus : c'était le défaut signalé — le formulaire
 *  offrait « Images », qui *est* la durée du plan, sans que rien ne le
 *  dise. Personne ne cherche « 97 » quand il veut quatre secondes. */
const CHAMPS: Record<string, { libelle: string; min: number; max: number; pas: number; aide?: string }> = {
  etapes: { libelle: "Étapes", min: 1, max: 50, pas: 1,
            aide: "LTX est distillé : au-delà de 8, il ne gagne rien. SDXL en demande 25." },
  // « 0 pour laisser courir » était faux, et c'est le piège que le dé
  // corrige : 0 est une graine comme une autre, pas un tirage. Deux
  // rendus lancés sans y toucher donnaient donc exactement le même
  // fichier — ce que personne n'attend d'un bouton « Lancer ».
  graine: { libelle: "Graine", min: 0, max: 999999, pas: 1,
            aide: "Même graine + mêmes réglages = le même plan, à l'identique. Le dé en tire une nouvelle." },
  cfg: { libelle: "CFG", min: 1, max: 20, pas: 0.5,
         aide: "Combien le modèle colle à la consigne. 7 est la référence SDXL." },
};

/** Les cadences proposées. 24 est la seule mesurée sur ce projet — les
 *  autres sont offertes parce que le gabarit les accepte, et étiquetées
 *  comme non mesurées plutôt que présentées comme équivalentes. */
const CADENCES = [
  { v: 24, nom: "24", note: "cadence de tous les plans mesurés" },
  { v: 25, nom: "25", note: "non mesurée" },
  { v: 30, nom: "30", note: "non mesurée" },
];

export function Composer({ actif }: { actif: boolean }) {
  const { data: catalogue } = useStudioTemplates();
  const { data: calibration } = useStudioCalibration();
  const calibrer = useStudioCalibrer();
  const lancer = useStudioCompose();

  const [gabarit, setGabarit] = useState("plan_video");
  const [consigne, setConsigne] = useState("");
  const [format, setFormat] = useState("paysage");
  const [valeurs, setValeurs] = useState<Record<string, number>>({
    etapes: 8, graine: 0, cfg: 7,
  });
  const [avecSon, setAvecSon] = useState(false);
  // La durée est l'état que l'opérateur manipule ; les images en sont
  // dérivées à la soumission. L'inverse — stocker des images et afficher
  // une durée — ferait sauter le curseur d'un cran à l'autre à chaque
  // frappe, l'arrondi remontant dans le champ qu'on est en train de
  // remplir.
  const [duree, setDuree] = useState(2);
  const [cadence, setCadence] = useState(24);
  const [negatif, setNegatif] = useState("");
  const [prefixe, setPrefixe] = useState("");
  const [interpolation, setInterpolation] = useState("aucune");
  const [imageDepart, setImageDepart] = useState("");

  if (!catalogue) {
    return <Card title="Rendu"><p className="text-xs text-hermes-dim">Chargement des gabarits…</p></Card>;
  }

  const fiche: GabaritDTO | undefined = catalogue.gabarits[gabarit];
  const attendus = new Set(fiche?.parametres ?? []);
  const offerts = fiche?.formats ?? Object.keys(catalogue.formats);

  // Un format valide pour LTX ruine un rendu SDXL. Mesuré : le premier
  // formulaire offrait la même liste aux deux, un SDXL est parti en
  // 768 × 432 et l'image est sortie tuilée et déformée. On retombe donc
  // toujours sur un format que le moteur choisi sait rendre.
  const formatEffectif = offerts.includes(format) ? format : offerts[0];
  const dims = catalogue.formats[formatEffectif];

  // La contrainte vient du backend, pas d'une constante recopiée ici :
  // LTX n'accepte que des longueurs `8k + 1`, et c'est `gabarits.py` qui
  // le sait. Les valeurs de repli ne servent qu'au premier rendu, avant
  // que le catalogue ne soit arrivé.
  const pas = catalogue.images?.pas ?? 8;
  const imagesMax = catalogue.images?.max ?? 257;
  const imagesPourDuree = (s: number, c: number) =>
    Math.max(1, Math.min(imagesMax, Math.round((Math.max(0, s) * c) / pas) * pas + 1));

  const images = imagesPourDuree(duree, cadence);
  // Ce que le rendu durera vraiment. L'image supplémentaire de `8k + 1`
  // fait 2,04 s là où l'on a demandé 2,00 — l'écart est petit, mais
  // l'afficher coûte une ligne et l'arrondir en silence ferait annoncer
  // une durée qui n'est pas rendue.
  const dureeReelle = images / cadence;
  const dureePlafonnee = images >= imagesMax;

  // Le temps de calcul suit les **pixels autant que les images**, ce que
  // « 5 min par seconde de vidéo » ignorait : cette règle venait du seul
  // rendu vertical et surestimait de 144 % en 768×432. Annoncer vingt
  // minutes pour un rendu qui en prend quatre décourage un essai qui
  // aurait été bon marché.
  const coutFixe = catalogue.cout?.fixe_s ?? 56;
  const coutParMpx = catalogue.cout?.par_mpx_image_s ?? 13.27;
  const minutesCalcul =
    (coutFixe + coutParMpx * ((dims?.largeur ?? 0) * (dims?.hauteur ?? 0) * images) / 1e6) / 60;

  const soumettre = () => {
    const parametres: Record<string, unknown> = { format_: formatEffectif };
    for (const [cle, v] of Object.entries(valeurs)) {
      if (attendus.has(cle)) parametres[cle] = v;
    }
    // La durée ne part pas telle quelle : le nœud attend une longueur en
    // images, et c'est elle qu'on envoie.
    if (attendus.has("images")) parametres.images = images;
    if (attendus.has("cadence")) parametres.cadence = cadence;
    if (attendus.has("avec_son")) parametres.avec_son = avecSon;
    // Vides, ces deux-là ne partent pas : le gabarit a ses propres
    // défauts mesurés, et envoyer une chaîne vide les écraserait — un
    // prompt négatif vide n'est pas « le prompt négatif par défaut ».
    if (attendus.has("negatif") && negatif.trim()) parametres.negatif = negatif.trim();
    if (attendus.has("prefixe") && prefixe.trim()) parametres.prefixe = prefixe.trim();
    if (attendus.has("interpolation") && interpolation !== "aucune") parametres.interpolation = interpolation;
    if (attendus.has("image_depart") && imageDepart.trim()) parametres.image_depart = imageDepart.trim();
    lancer.mutate({ gabarit, consigne, parametres });
  };

  const reponse = lancer.data;

  return (
    <Card
      title="Rendu"
      subtitle={fiche ? `${fiche.moteur} — ${fiche.note}` : undefined}
      accent="amber"
    >
      <div className="flex flex-col gap-3">
        {/* Le gabarit d'abord : il décide de ce que les autres champs
            veulent dire. */}
        <div className="flex flex-wrap gap-2">
          {Object.entries(catalogue.gabarits).map(([cle, g]) => (
            <button
              key={cle}
              onClick={() => setGabarit(cle)}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-mono transition-all ${
                gabarit === cle
                  ? "border-hermes-amber/60 bg-hermes-amber/10 text-hermes-text"
                  : "border-hermes-border/50 text-hermes-muted hover:border-hermes-border"
              }`}
            >
              {g.sortie === "video" ? <Film size={11} /> : <ImageIcon size={11} />}
              {g.titre}
            </button>
          ))}
        </div>

        <textarea
          placeholder="Ce que le plan doit montrer — en anglais, c'est la langue des deux modèles…"
          value={consigne}
          onChange={(e) => setConsigne(e.target.value)}
          rows={3}
          className="resize-none rounded-lg border border-hermes-border bg-hermes-bg px-3 py-2
            font-mono text-sm text-hermes-text outline-none focus:border-hermes-amber"
        />

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="tech-label">Format</span>
            <select
              value={formatEffectif}
              onChange={(e) => setFormat(e.target.value)}
              className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
            >
              {offerts.map((nom) => (
                <option key={nom} value={nom}>
                  {nom} — {catalogue.formats[nom]?.largeur}×
                  {catalogue.formats[nom]?.hauteur}
                </option>
              ))}
            </select>
          </label>

          {/* La durée, en secondes — ce que l'opérateur a en tête. Le
              champ « Images » qu'elle remplace disait la même chose dans
              l'unité du modèle, ce qui revenait à ne pas la proposer. */}
          {attendus.has("images") && (
            <label className="flex flex-col gap-1">
              <span className="tech-label">Durée (s)</span>
              <input
                type="number"
                min={1}
                max={Math.floor((imagesMax - 1) / cadence)}
                step={0.5}
                value={duree}
                onChange={(e) => setDuree(Number(e.target.value))}
                className="w-24 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                  font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
              />
            </label>
          )}

          {attendus.has("cadence") && (
            <label className="flex flex-col gap-1">
              <span className="tech-label">Cadence</span>
              <select
                value={cadence}
                onChange={(e) => setCadence(Number(e.target.value))}
                className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                  font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
              >
                {CADENCES.map((c) => (
                  <option key={c.v} value={c.v} title={c.note}>
                    {c.nom} im/s{c.v === 24 ? "" : " ·"}
                  </option>
                ))}
              </select>
            </label>
          )}

          {Object.entries(CHAMPS)
            .filter(([cle]) => attendus.has(cle))
            .map(([cle, c]) => (
              <label key={cle} className="flex flex-col gap-1" title={c.aide}>
                <span className="tech-label">{c.libelle}</span>
                <input
                  type="number"
                  min={c.min}
                  max={c.max}
                  step={c.pas}
                  value={valeurs[cle]}
                  onChange={(e) =>
                    setValeurs((v) => ({ ...v, [cle]: Number(e.target.value) }))
                  }
                  className="w-24 rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                    font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                />
              </label>
            ))}

          {/* Le dé. Sans lui, la graine reste à 0 — une valeur fixe, pas
              un tirage — et deux lancements consécutifs rendent le même
              plan. */}
          {attendus.has("graine") && (
            <button
              onClick={() => setValeurs((v) => ({
                ...v, graine: Math.floor(Math.random() * 1_000_000),
              }))}
              title="Tirer une nouvelle graine"
              className="mb-[1px] flex items-center gap-1.5 rounded-lg border border-hermes-border
                px-2.5 py-1.5 font-mono text-[11px] text-hermes-muted transition-all
                hover:border-hermes-amber/40 hover:text-hermes-amber"
            >
              <Dices size={12} /> Nouvelle
            </button>
          )}

          {attendus.has("avec_son") && (
            <label className="flex cursor-pointer items-center gap-2 pb-1.5">
              <input
                type="checkbox"
                checked={avecSon}
                onChange={(e) => setAvecSon(e.target.checked)}
                className="accent-hermes-sodium"
              />
              <span className="tech-label">Son natif (+21 %)</span>
            </label>
          )}
        </div>

        {/* Lissage et enchaînement (HOS-200). Deux réglages dont l'effet
            se paie au rendu, donc annoncés ici plutôt que découverts
            après coup. */}
        {(attendus.has("interpolation") || attendus.has("image_depart")) && (
          <div className="flex flex-wrap items-end gap-3">
            {attendus.has("interpolation") && (
              <label className="flex flex-col gap-1">
                <span className="tech-label">Lissage</span>
                <select
                  value={interpolation}
                  onChange={(e) => setInterpolation(e.target.value)}
                  className="rounded-lg border border-hermes-border bg-hermes-bg px-2 py-1.5
                    font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                >
                  <option value="aucune">aucun</option>
                  <option value="film">FILM — le seul qui réduit la secousse</option>
                  <option value="rife">RIFE — plus rapide, aggrave la secousse</option>
                  <option value="rife_heavy">RIFE lourd</option>
                </select>
              </label>
            )}

            {attendus.has("image_depart") && (
              <label className="flex min-w-[240px] flex-1 flex-col gap-1">
                <span className="tech-label">Partir d&apos;une image (optionnel)</span>
                <div className="flex items-center gap-1.5">
                  <Link2 size={12} className="shrink-0 text-hermes-dim" />
                  <input
                    type="text"
                    value={imageDepart}
                    onChange={(e) => setImageDepart(e.target.value)}
                    placeholder="nom d'une image du dossier d'entrée de ComfyUI"
                    className="w-full rounded-lg border border-hermes-border bg-hermes-bg px-3 py-1.5
                      font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                  />
                </div>
              </label>
            )}
          </div>
        )}

        {/* Ce que le lissage ne fait pas, dit avant le clic. */}
        {interpolation !== "aucune" && (
          <p className="text-[11px] leading-relaxed text-hermes-gold">
            Le lissage double la cadence sans changer la durée. Il ne supprime
            pas l&apos;irrégularité de fond : celle-ci vient de la structure
            temporelle du modèle (8 images par image latente), et aucun des
            trois modèles mesurés ne l&apos;efface.
          </p>
        )}

        {/* Ce que le départ sur image exige, avant que le rendu n'échoue. */}
        {imageDepart.trim() && dims && (dims.largeur % 32 !== 0 || dims.hauteur % 32 !== 0) && (
          <p className="text-[11px] leading-relaxed text-hermes-alarm">
            {dims.largeur} × {dims.hauteur} ne convient pas : partir d&apos;une image
            exige des côtés multiples de 32. Choisissez un format « suite », ou
            le portrait.
          </p>
        )}

        {/* Prompt négatif et préfixe : implémentés dans les gabarits
            depuis HOS-194 et jamais offerts, donc inaccessibles autrement
            qu'en passant par l'agent. Laissés vides, le gabarit garde ses
            propres défauts mesurés. */}
        {(attendus.has("negatif") || attendus.has("prefixe")) && (
          <div className="flex flex-wrap gap-3">
            {attendus.has("negatif") && (
              <label className="flex min-w-[280px] flex-1 flex-col gap-1">
                <span className="tech-label">Ce qu&apos;il ne faut pas (optionnel)</span>
                <input
                  type="text"
                  value={negatif}
                  onChange={(e) => setNegatif(e.target.value)}
                  placeholder="blurry, distorted, watermark, text, low quality"
                  className="rounded-lg border border-hermes-border bg-hermes-bg px-3 py-1.5
                    font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                />
              </label>
            )}
            {attendus.has("prefixe") && (
              <label className="flex min-w-[200px] flex-col gap-1">
                <span className="tech-label">Nom du fichier (optionnel)</span>
                <input
                  type="text"
                  value={prefixe}
                  onChange={(e) => setPrefixe(e.target.value)}
                  placeholder={fiche?.sortie === "video" ? "studio/plan" : "studio/image"}
                  className="rounded-lg border border-hermes-border bg-hermes-bg px-3 py-1.5
                    font-mono text-[11px] text-hermes-text outline-none focus:border-hermes-amber"
                />
              </label>
            )}
          </div>
        )}

        {/* D'où vient le réglage du décodeur, et s'il a été éprouvé
            (HOS-210). La table des paliers vit dans le code et s'est
            révélée fausse deux fois : trop prudente, d'où le
            quadrillage, puis mal calibrée. Une mesure prise sur cette
            machine prime sur elle — encore faut-il que l'écran dise
            laquelle des deux il applique. */}
        {fiche?.sortie === "video" && dims && (
          <CalibrationDuPlan
            largeur={dims.largeur} hauteur={dims.hauteur} images={images}
            mesures={calibration?.mesures} calibrer={calibrer} />
        )}

        {/* Le coût, annoncé avant le clic. Cinq minutes de calcul par
            seconde de vidéo : c'est la chose la plus utile à savoir
            avant de lancer, et l'apprendre après serait une mauvaise
            surprise de vingt minutes.

            La durée affichée est celle qui sera **rendue**, pas celle qui
            a été tapée : `8k + 1` ajoute une image, et 2 s demandées font
            2,04 s. */}
        {fiche?.sortie === "video" && dims && (
          <p className="text-[11px] leading-relaxed text-hermes-dim">
            <span className="num text-hermes-muted">{dureeReelle.toFixed(2)} s</span> de vidéo
            en {dims.largeur}×{dims.hauteur} —{" "}
            <span className="num">{images} images</span> à {cadence} im/s. Compter environ{" "}
            <span className="num text-hermes-muted">
              {minutesCalcul < 1.5
                ? `${Math.round(minutesCalcul * 60)} s`
                : `${Math.round(minutesCalcul)} min`}
            </span>{" "}
            de calcul, la carte réservée pendant ce temps — extrapolé de trois
            rendus mesurés, à ±11 %.
            {dureePlafonnee && (
              <span className="text-hermes-gold">
                {" "}Plafonné à {imagesMax} images — c&apos;est la longueur maximale
                du gabarit.
              </span>
            )}
            {cadence !== 24 && (
              <span className="text-hermes-gold">
                {" "}Seule la cadence 24 a été mesurée sur cette carte.
              </span>
            )}
          </p>
        )}

        <div className="flex items-center justify-between gap-3">
          <div className="min-h-[18px] flex-1">
            {reponse && !reponse.success && (
              <div className="flex items-start gap-1.5">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-hermes-alarm" />
                <span className="text-[11px] leading-relaxed text-hermes-alarm">
                  {reponse.error}
                </span>
              </div>
            )}
            {reponse?.success && (
              <span className="num text-[11px] text-hermes-arc">
                soumis — {reponse.prompt_id?.slice(0, 8)}
                {reponse.modeles_decharges?.length
                  ? ` · déchargé ${reponse.modeles_decharges.join(", ")}`
                  : ""}
              </span>
            )}
            {lancer.isError && (
              <span className="text-[11px] text-hermes-alarm">
                {(lancer.error as Error).message}
              </span>
            )}
          </div>

          <button
            onClick={soumettre}
            disabled={!consigne.trim() || lancer.isPending || actif}
            title={actif ? "Un rendu occupe déjà la carte" : undefined}
            className="flex items-center gap-1.5 rounded-lg bg-hermes-amber px-4 py-1.5
              font-mono text-xs text-black transition-colors hover:bg-hermes-amber-bright
              disabled:opacity-40"
          >
            {lancer.isPending && <Loader2 size={12} className="animate-spin" />}
            {actif ? "Carte occupée" : lancer.isPending ? "Soumission…" : "Lancer"}
          </button>
        </div>
      </div>
    </Card>
  );
}

/** Dit si le réglage du décodeur a été mesuré pour ce plan précis.
 *
 *  Le défaut que ça évite : un rendu part, la diffusion tourne vingt
 *  minutes, et le décodage déborde à la fin. L'essai à blanc décode un
 *  latent **vide** aux mêmes dimensions — même chemin mémoire, aucun
 *  modèle de diffusion chargé — et le résultat est enregistré une fois
 *  pour toutes.
 */
function CalibrationDuPlan({ largeur, hauteur, images, mesures, calibrer }: {
  largeur: number; hauteur: number; images: number;
  mesures?: Record<string, { tuile: number; mesure_le?: string }>;
  calibrer: ReturnType<typeof useStudioCalibrer>;
}) {
  const cle = `${largeur}x${hauteur}x${images}`;
  const mesure = mesures?.[cle];

  if (mesure) {
    return (
      <p className="flex items-center gap-1.5 text-[11px] text-hermes-arc">
        <CheckCircle2 size={12} className="shrink-0" />
        Décodage éprouvé sur cette machine — tuile {mesure.tuile}
        {mesure.mesure_le ? `, mesurée le ${mesure.mesure_le}` : ""}.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <p className="flex-1 text-[11px] leading-relaxed text-hermes-gold">
        Ce format et cette durée n&apos;ont jamais été mesurés ici. Le réglage
        vient d&apos;une table écrite dans le code, qui s&apos;est déjà révélée
        fausse — un débordement se produirait <strong>après</strong> la
        diffusion, donc après tout le temps de calcul.
      </p>
      <button
        onClick={() => calibrer.mutate({ largeur, hauteur, images })}
        disabled={calibrer.isPending}
        title="Décode un latent vide aux mêmes dimensions, en partant du réglage de la table : un à trois essais de quelques minutes chacun"
        className="flex shrink-0 items-center gap-1.5 rounded-lg border border-hermes-gold/40
          px-3 py-1.5 font-mono text-[11px] text-hermes-gold transition-all
          hover:bg-hermes-gold/10 disabled:opacity-40"
      >
        {calibrer.isPending ? <Loader2 size={12} className="animate-spin" /> : <Gauge size={12} />}
        {calibrer.isPending ? "Mesure en cours…" : "Mesurer maintenant"}
      </button>
      {calibrer.data && !calibrer.data.success && (
        <span className="w-full text-[11px] text-hermes-alarm">
          {calibrer.data.error}
        </span>
      )}
    </div>
  );
}

export default Composer;
