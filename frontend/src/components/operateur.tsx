"use client";

import { memo } from "react";

/**
 * L'opérateur (HOS-182).
 *
 * Une figure dessinée en aplats pleins, posée dans le coin de l'écran, qui
 * prend une posture différente selon ce que le système est réellement en
 * train de faire. Elle ne remplace aucun chiffre : elle donne au coin de
 * l'œil ce qu'il faut aujourd'hui chercher dans un journal — *est-ce que ça
 * travaille, et à quoi*.
 *
 * ## Ce qui la rend légitime plutôt que décorative
 *
 * Chaque posture est branchée sur un topic que le backend publie vraiment
 * (voir `use-operateur.ts`). Aucune n'est déclenchée par une minuterie.
 * Quand rien n'est signalé, la posture est `repos` — y compris si une
 * mission tourne, auquel cas le repos est l'information : le système ne
 * rapporte rien. C'est la règle du projet appliquée à l'interface, un
 * succès ne se croit pas sur parole et une activité non plus.
 *
 * ## Dessin
 *
 * Trois règles, chacune apprise après l'avoir vue rater à l'écran :
 *
 * * Les membres sont des tubes tracés deux fois — une passe sombre large
 *   qui fait le contour, une passe claire plus fine par-dessus. Ils doivent
 *   sortir de la silhouette du torse, sinon ils s'y fondent et le
 *   personnage n'a plus de bras.
 * * La tête fait un tiers de la hauteur. En dessous, le registre bascule
 *   vers la figurine technique.
 * * Les objets tenus sont en négatif — fond sombre, contour clair. Dessinés
 *   comme le corps, ils se lisaient comme un motif de vêtement. Et ils se
 *   tiennent à l'écart de la tête : une loupe à hauteur d'oreille se
 *   confondait avec la coque du casque.
 *
 * L'identité vient d'Hermès : le casque porte les petites ailes du pétase,
 * l'attribut du messager. Ce n'est ni un emprunt ni une citation.
 *
 * ## Pourquoi `memo`
 *
 * Une animation CSS repart de zéro quand son élément est démonté. Le
 * Cockpit rafraîchit sa télémétrie à la seconde ; sans mémoïsation,
 * l'opérateur recommencerait son geste à chaque relevé sans jamais
 * l'achever. Il ne doit se re-rendre que lorsque l'`etat` change.
 */

export type EtatOperateur =
  | "repos"
  | "lancement"
  | "reflexion"
  | "lecture"
  | "ecriture"
  | "verification"
  | "tests"
  | "reussite"
  | "chargement"
  | "debordement"
  | "defaut"
  | "alerte"
  | "decision"
  | "ecoute"
  | "parole";

type Visage =
  | "normal" | "clin" | "heureux" | "concentre"
  | "pense" | "effort" | "inquiet" | "parle";

interface Posture {
  libelle: string;
  teinte: string;
  visage: Visage;
  /** Durée d'un tour complet, telle qu'écrite dans les images-clés. */
  boucle: string;
  corps: string;
  tete?: string;
  brasG?: string;
  brasD?: string;
  bg: string;
  mg: readonly [number, number, number];
  bd: string;
  md: readonly [number, number, number];
  pouceD?: boolean;
  objet?: "feuille" | "planchette" | "liste" | "caisse" | "grosseCaisse" | "tendu";
  main?: "loupe" | "chrono";
  signe?: "rouages" | "gouttes" | "panneau" | "eclats" | "ondesEntrantes" | "ondesSortantes";
}

/** Chaque état est une posture complète : deux bras, un visage, une boucle
 *  et éventuellement un objet. Déclaré ici plutôt que dispersé dans le
 *  rendu — on lit une posture d'un coup. */
export const POSTURES: Record<EtatOperateur, Posture> = {
  repos: {
    libelle: "Au repos", teinte: "#8695a6", visage: "normal", corps: "a-repos", boucle: "7,6 s",
    bg: "M72,152 C56,162 50,182 52,196", mg: [52, 202, 0],
    bd: "M138,152 C154,162 160,182 158,196", md: [158, 202, 0],
  },
  lancement: {
    libelle: "Tâche lancée", teinte: "#ff9436", visage: "clin", corps: "a-rebond", boucle: "2,6 s",
    bg: "M72,152 C54,160 46,180 58,192", mg: [62, 198, 0],
    bd: "M138,152 C162,156 172,138 166,118", md: [166, 112, 8], pouceD: true, brasD: "a-pouce",
  },
  reflexion: {
    libelle: "Réflexion", teinte: "#ff9436", visage: "pense", corps: "a-souffle", boucle: "1,7 s",
    bg: "M72,152 C54,160 46,180 58,192", mg: [62, 198, 0],
    bd: "M138,152 C164,162 162,134 140,122", md: [134, 118, -36], brasD: "a-tapote",
    signe: "rouages",
  },
  lecture: {
    libelle: "Lecture", teinte: "#5eb8e8", visage: "concentre", corps: "a-souffle", boucle: "2,4 s",
    bg: "M72,152 C62,164 56,180 56,190", mg: [56, 196, 0],
    bd: "M138,152 C148,164 154,180 154,190", md: [154, 196, 0],
    objet: "feuille", tete: "a-lit",
  },
  ecriture: {
    libelle: "Écriture", teinte: "#ff9436", visage: "concentre", corps: "a-souffle", boucle: "3,6 s",
    bg: "M72,152 C58,166 48,190 48,206", mg: [48, 212, 0],
    bd: "M138,152 C160,164 148,196 118,202", md: [112, 206, 34], brasD: "a-ecrit",
    objet: "planchette",
  },
  verification: {
    libelle: "Vérification", teinte: "#ffc93d", visage: "concentre", corps: "a-souffle", boucle: "3,2 s",
    bg: "M72,152 C56,162 50,182 54,196", mg: [56, 202, 0],
    bd: "M138,152 C158,154 172,146 178,134", md: [180, 130, -6], main: "loupe", brasD: "a-fouille",
  },
  tests: {
    libelle: "Tests", teinte: "#ff9436", visage: "concentre", corps: "a-souffle", boucle: "3,6 s",
    bg: "M72,152 C56,166 46,192 46,208", mg: [46, 214, 0],
    bd: "M138,152 C160,152 176,144 184,136", md: [186, 134, 10], main: "chrono",
    objet: "liste",
  },
  reussite: {
    libelle: "Réussi", teinte: "#9ede3a", visage: "heureux", corps: "a-saute", boucle: "1,35 s",
    bg: "M72,152 C52,136 40,110 36,88", mg: [34, 82, -28],
    bd: "M138,152 C158,136 170,110 174,88", md: [176, 82, 28],
  },
  chargement: {
    libelle: "Chargement du modèle", teinte: "#ff9436", visage: "concentre", corps: "a-porte", boucle: "4 s",
    bg: "M72,152 C60,162 54,178 56,188", mg: [56, 194, 0],
    bd: "M138,152 C150,162 156,178 154,188", md: [154, 194, 0],
    objet: "caisse",
  },
  debordement: {
    libelle: "Débordement — chemin CPU", teinte: "#ff5347", visage: "effort", corps: "a-effort", boucle: "2,6 s",
    bg: "M72,152 C54,166 42,192 42,204", mg: [42, 210, 0],
    bd: "M138,152 C156,166 168,192 168,204", md: [168, 210, 0],
    objet: "grosseCaisse", signe: "gouttes",
  },
  defaut: {
    libelle: "Défaut relevé", teinte: "#ffc93d", visage: "inquiet", corps: "a-souffle", boucle: "1,6 s",
    bg: "M72,152 C54,160 46,180 58,192", mg: [62, 198, 0],
    bd: "M138,152 C166,156 180,144 184,126", md: [186, 120, 14], brasD: "a-jab",
    signe: "panneau",
  },
  alerte: {
    libelle: "Alerte", teinte: "#ff5347", visage: "inquiet", corps: "a-agite", boucle: "0,62 s",
    bg: "M72,152 C50,148 40,124 50,104", mg: [52, 98, -20], brasG: "a-vague-g",
    bd: "M138,152 C160,148 170,124 160,104", md: [158, 98, 20], brasD: "a-vague-d",
    signe: "eclats",
  },
  decision: {
    libelle: "Décision attendue", teinte: "#5eb8e8", visage: "normal", corps: "a-tend", boucle: "2,4 s",
    bg: "M72,152 C60,162 54,176 56,186", mg: [56, 192, 0],
    bd: "M138,152 C150,162 156,176 154,186", md: [154, 192, 0],
    objet: "tendu",
  },
  // Les deux postures du Voice Center. Écoute en glacier parce que c'est
  // l'humain qui parle — la couleur du point de décision humaine dans ce
  // système ; parole en sodium, c'est le système qui répond.
  ecoute: {
    libelle: "À l'écoute", teinte: "#5eb8e8", visage: "concentre", corps: "a-souffle", boucle: "1,8 s",
    bg: "M72,152 C56,162 50,182 52,196", mg: [52, 202, 0],
    bd: "M138,152 C166,158 176,132 160,110", md: [156, 104, -26],
    tete: "a-tend-oreille", signe: "ondesEntrantes",
  },
  parole: {
    libelle: "Synthèse vocale", teinte: "#ff9436", visage: "parle", corps: "a-souffle", boucle: "0,62 s",
    bg: "M72,152 C56,162 50,182 52,196", mg: [52, 202, 0],
    bd: "M138,152 C154,162 160,182 158,196", md: [158, 202, 0],
    signe: "ondesSortantes",
  },
};

/** Un engrenage se calcule ; écrit à la main il devient une étoile. */
function engrenage(cx: number, cy: number, rExt: number, rInt: number, dents: number): string {
  const n = dents * 2;
  const pts: string[] = [];
  for (let i = 0; i < n; i++) {
    const r = i % 2 === 0 ? rExt : rInt;
    const a = (Math.PI * 2 * i) / n;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`);
  }
  return `M${pts.join(" L")} Z`;
}

const ENGRENAGE_A = engrenage(168, 34, 18, 12.5, 8);
const ENGRENAGE_B = engrenage(199, 12, 12, 8, 6);

function Main({
  x, y, r, pouce, outil,
}: {
  x: number; y: number; r: number;
  pouce?: boolean;
  outil?: "loupe" | "chrono";
}) {
  return (
    <g transform={`translate(${x}, ${y}) rotate(${r})`}>
      {outil === "loupe" && (
        <g>
          <path className="o-tr" d="M0,-14 L0,2" strokeWidth={13} />
          <path className="o-tp" d="M0,-14 L0,2" strokeWidth={7} />
          <circle className="o-f" cx={0} cy={-34} r={20} />
          <circle fill="var(--ombre)" cx={0} cy={-34} r={12} />
          <path className="a-reflet" d="M-4,-42 L2,-26" fill="none"
            stroke="var(--corps)" strokeWidth={3.6} strokeLinecap="round" />
        </g>
      )}
      {outil === "chrono" && (
        <g>
          <path className="o-f" d="M-6,-50 h12 v8 h-12 z" />
          <circle className="o-f" cx={0} cy={-28} r={18} />
          <path className="o-l a-aiguille" d="M0,-28 L0,-40" strokeWidth={3.4} />
          <circle className="o-d" cx={0} cy={-28} r={2.6} />
        </g>
      )}
      {pouce && <path className="o-f" d="M-3,-9 C-11,-14 -11,-28 -2,-29 C7,-30 10,-19 7,-9 Z" />}
      <circle className="o-f" cx={0} cy={0} r={12.5} />
      <path className="o-lf" d="M-7,-4 h14 M-6,2.5 h12" />
    </g>
  );
}

function Objet({ nom }: { nom: NonNullable<Posture["objet"]> }) {
  switch (nom) {
    case "feuille":
      return (
        <g className="a-page">
          <path className="o-p" d="M52,158 h106 v72 h-106 z" />
          <path className="o-pl" d="M64,176 h82 M64,190 h82 M64,204 h58 M64,218 h70" />
          <path className="a-balaye" d="M54,168 h102" fill="none"
            stroke="var(--corps)" strokeWidth={4.5} opacity={0.9} />
        </g>
      );
    case "planchette":
      return (
        <g>
          <path className="o-p" d="M38,166 h84 v86 h-84 z" />
          <path className="o-f" d="M66,158 h28 v15 h-28 z" />
          <path className="o-pl a-ligne-1" d="M50,192 h64" />
          <path className="o-pl a-ligne-2" d="M50,210 h64" />
          <path className="o-pl a-ligne-3" d="M50,228 h64" />
        </g>
      );
    case "liste":
      return (
        <g>
          <path className="o-p" d="M36,164 h84 v88 h-84 z" />
          <path className="o-f" d="M64,156 h28 v15 h-28 z" />
          <path className="o-pl" d="M48,186 h12 v12 h-12 z M48,208 h12 v12 h-12 z M48,230 h12 v12 h-12 z" />
          <path className="o-pl" d="M70,192 h38 M70,214 h38 M70,236 h24" opacity={0.45} />
          <path className="a-coche-1" d="M49,192 l4,5 l7,-9" fill="none"
            stroke="var(--corps)" strokeWidth={3.4} strokeLinecap="round" />
          <path className="a-coche-2" d="M49,214 l4,5 l7,-9" fill="none"
            stroke="var(--corps)" strokeWidth={3.4} strokeLinecap="round" />
          <path className="a-coche-3" d="M49,236 l4,5 l7,-9" fill="none"
            stroke="var(--corps)" strokeWidth={3.4} strokeLinecap="round" />
        </g>
      );
    case "caisse":
      return (
        <g>
          <path className="o-p" d="M56,162 h98 v68 h-98 z" />
          <path className="a-remplit" d="M58,164 h94 v64 h-94 z" fill="var(--corps)" opacity={0.26} />
          <path className="o-pl" d="M56,178 h98 M56,214 h98 M84,162 v68 M126,162 v68" />
        </g>
      );
    case "grosseCaisse":
      return (
        <g>
          <path className="o-p" d="M30,152 h150 v100 h-150 z" />
          <path className="o-pl" d="M30,174 h150 M30,230 h150 M72,152 v100 M138,152 v100" />
          <path className="o-pl" d="M76,204 h58" opacity={1} />
        </g>
      );
    case "tendu":
      return (
        <g>
          <path className="o-p" d="M48,150 h114 v88 h-114 z" />
          <path className="o-f" d="M92,142 h30 v15 h-30 z" />
          <path className="o-pl" d="M62,176 h86 M62,194 h86 M62,212 h50" />
          <path className="o-pl" d="M110,220 h38" opacity={1} />
        </g>
      );
  }
}

function Visage({ nom }: { nom: Visage }) {
  switch (nom) {
    case "normal":
      return (
        <g>
          <g className="a-cligne">
            <ellipse className="o-d" cx={88} cy={80} rx={5.4} ry={7.4} />
            <ellipse className="o-d" cx={122} cy={80} rx={5.4} ry={7.4} />
          </g>
          <path className="o-l" d="M76,63 Q88,57 98,62 M112,62 Q122,57 134,63" />
          <path className="o-l" d="M105,86 Q111,100 99,100" />
          <path className="o-l" d="M80,106 Q105,126 130,106" />
        </g>
      );
    case "clin":
      return (
        <g>
          <ellipse className="o-d" cx={88} cy={80} rx={5.4} ry={7.4} />
          <path className="o-l" d="M113,82 Q122,73 131,82" strokeWidth={4.6} />
          <path className="o-l" d="M76,63 Q88,57 98,62 M111,59 Q122,53 134,60" />
          <path className="o-l" d="M105,86 Q111,100 99,100" />
          <path className="o-l" d="M78,104 Q105,128 131,103" />
          <path className="o-lf" d="M128,111 Q135,109 138,103" />
        </g>
      );
    case "heureux":
      return (
        <g>
          <path className="o-l" d="M79,82 Q88,70 97,82 M113,82 Q122,70 131,82" strokeWidth={4.8} />
          <path className="o-l" d="M105,88 Q111,100 99,100" />
          <path className="o-f" d="M78,104 Q105,134 132,104 Z" />
        </g>
      );
    case "concentre":
      return (
        <g>
          <ellipse className="o-d" cx={87} cy={82} rx={5} ry={5.2} />
          <ellipse className="o-d" cx={121} cy={82} rx={5} ry={5.2} />
          <path className="o-l" d="M75,68 Q87,62 98,68 M110,68 Q121,62 133,68" />
          <path className="o-l" d="M105,88 Q111,101 99,101" />
          <path className="o-l" d="M86,112 Q105,119 124,111" />
        </g>
      );
    case "pense":
      return (
        <g>
          <ellipse className="o-d" cx={92} cy={75} rx={5.2} ry={6.6} />
          <ellipse className="o-d" cx={126} cy={75} rx={5.2} ry={6.6} />
          <path className="o-l" d="M78,60 Q90,53 100,59 M113,59 Q124,53 136,60" />
          <path className="o-l" d="M105,86 Q111,100 99,100" />
          <path className="o-l" d="M89,113 Q105,107 121,114" />
        </g>
      );
    case "effort":
      return (
        <g>
          <path className="o-l" d="M79,73 l9,8 l-9,8 M131,73 l-9,8 l9,8" strokeWidth={4.6} />
          <path className="o-l" d="M105,88 Q111,100 99,100" />
          <path className="o-f" d="M86,106 h38 a6,6 0 0 1 6,6 v4 a6,6 0 0 1 -6,6 h-38 a6,6 0 0 1 -6,-6 v-4 a6,6 0 0 1 6,-6 z" />
          <path className="o-lf" d="M95,106 v16 M115,106 v16" />
        </g>
      );
    case "inquiet":
      return (
        <g>
          <circle className="o-d" cx={88} cy={80} r={7.4} />
          <circle className="o-d" cx={124} cy={80} r={7.4} />
          <path className="o-l" d="M74,60 Q86,55 97,64 M114,64 Q125,55 137,60" />
          <path className="o-l" d="M105,88 Q111,101 99,101" />
          <ellipse className="o-d" cx={105} cy={114} rx={10} ry={11} />
        </g>
      );
    case "parle":
      return (
        <g>
          <g className="a-cligne">
            <ellipse className="o-d" cx={88} cy={80} rx={5.4} ry={7.4} />
            <ellipse className="o-d" cx={122} cy={80} rx={5.4} ry={7.4} />
          </g>
          <path className="o-l" d="M76,63 Q88,57 98,62 M112,62 Q122,57 134,63" />
          <path className="o-l" d="M105,86 Q111,100 99,100" />
          <ellipse className="o-d a-parle" cx={105} cy={110} rx={13} ry={9} />
        </g>
      );
  }
}

function Signe({ nom }: { nom: NonNullable<Posture["signe"]> }) {
  switch (nom) {
    case "rouages":
      return (
        <g>
          <g className="a-rouages">
            <path className="o-f" d={ENGRENAGE_A} />
            <circle className="o-d" cx={168} cy={34} r={5} />
          </g>
          <g className="a-rouages-b">
            <path className="o-f" d={ENGRENAGE_B} />
          </g>
        </g>
      );
    case "gouttes":
      return (
        <g>
          <g className="a-goutte">
            <path className="o-f" d="M42,84 C36,92 33,98 37,102 C41,106 47,103 47,97 C47,93 45,89 42,84 Z" />
          </g>
          <g className="a-goutte" style={{ animationDelay: "1.3s" }}>
            <path className="o-f" d="M170,88 C164,96 161,102 165,106 C169,110 175,107 175,101 C175,97 173,93 170,88 Z" />
          </g>
        </g>
      );
    case "panneau":
      return (
        <g className="a-battement">
          <path className="o-f" d="M184,66 L210,110 L158,110 Z" />
          <path className="o-d" d="M181,82 h6 v14 h-6 z M181,100 h6 v6 h-6 z" />
        </g>
      );
    case "eclats":
      return (
        <g className="a-eclat">
          <path className="o-l" d="M105,4 v13 M62,12 l6,12 M148,12 l-6,12 M28,38 l11,7 M182,38 l-11,7" strokeWidth={6} />
        </g>
      );
    // Les ondes entrent vers l'oreille quand l'humain parle, sortent du
    // micro quand c'est le système. Le sens du mouvement dit qui parle.
    case "ondesEntrantes":
      return (
        <g>
          <path className="o-l a-onde-1" d="M190,64 A26,26 0 0 1 190,116" fill="none" strokeWidth={4.5} />
          <path className="o-l a-onde-2" d="M200,52 A40,40 0 0 1 200,128" fill="none" strokeWidth={4.5} />
          <path className="o-l a-onde-3" d="M210,40 A54,54 0 0 1 210,140" fill="none" strokeWidth={4.5} />
        </g>
      );
    case "ondesSortantes":
      return (
        <g>
          <path className="o-l a-onde-1" d="M132,140 A22,22 0 0 0 132,184" fill="none" strokeWidth={4.5} />
          <path className="o-l a-onde-2" d="M124,132 A34,34 0 0 0 124,192" fill="none" strokeWidth={4.5} />
          <path className="o-l a-onde-3" d="M116,124 A46,46 0 0 0 116,200" fill="none" strokeWidth={4.5} />
        </g>
      );
  }
}

export interface OperateurProps {
  etat: EtatOperateur;
  /** Largeur en pixels. La hauteur suit le rapport 220 × 300. */
  taille?: number;
  className?: string;
}

function OperateurBrut({ etat, taille = 150, className = "" }: OperateurProps) {
  const p = POSTURES[etat] ?? POSTURES.repos;

  return (
    <svg
      className={`o-svg ${className}`}
      viewBox="0 0 220 300"
      width={taille}
      height={(taille * 300) / 220}
      style={{ ["--corps" as string]: p.teinte, ["--ombre" as string]: "#080a0d", display: "block", overflow: "visible" }}
      role="img"
      aria-label={`Opérateur Hermes — ${p.libelle}`}
    >
      <g className={p.corps}>
        {/* Jambes et bottes */}
        <g>
          <path className="o-tr" d="M88,214 L85,254" />
          <path className="o-tr" d="M122,214 L125,254" />
          <path className="o-tp" d="M88,214 L85,254" />
          <path className="o-tp" d="M122,214 L125,254" />
          <path className="o-f" d="M66,251 h22 a4,4 0 0 1 4,4 v13 a4,4 0 0 1 -4,4 H66 a5,5 0 0 1 -5,-5 v-11 a5,5 0 0 1 5,-5 z" />
          <path className="o-f" d="M132,251 h22 a5,5 0 0 1 5,5 v11 a5,5 0 0 1 -5,5 h-22 a4,4 0 0 1 -4,-4 v-13 a4,4 0 0 1 4,-4 z" />
        </g>

        {/* Cou et torse */}
        <g>
          <path className="o-f" d="M92,116 h26 v28 h-26 z" />
          <path className="o-f" d="M105,136 C117,136 127,139 134,145 C142,152 146,163 146,177 L146,205 C146,213 140,219 132,219 L78,219 C70,219 64,213 64,205 L64,177 C64,163 68,152 76,145 C83,139 93,136 105,136 Z" />
          <path className="o-l" d="M90,139 L105,158 L120,139" />
          <path className="o-f" d="M62,200 h86 v17 h-86 z" />
          <path className="o-d" d="M97,204 h16 v10 h-16 z" />
          <path className="o-l" d="M131,164 l9,5 v10 l-9,5 l-9,-5 v-10 z" strokeWidth={3} />
        </g>

        {p.objet && <Objet nom={p.objet} />}

        {/* Tête */}
        <g className={p.tete ?? ""}>
          {/* Ailes du pétase, posées haut aux tempes : plus bas elles se
              lisaient comme des moustaches. */}
          <path className="o-f" d="M52,62 C38,48 20,41 8,43 C17,55 28,61 40,64 C29,65 19,68 14,74 C25,81 40,81 52,75 Z" opacity={0.5} />
          <path className="o-f" d="M158,60 C172,44 192,36 206,38 C196,50 184,58 171,62 C183,62 194,66 199,72 C187,80 171,80 158,74 Z" />

          <ellipse className="o-f" cx={50} cy={88} rx={9} ry={12} />
          <path className="o-f" d="M105,26 C136,26 160,48 160,78 C160,102 146,120 127,126 C120,128 112,129 105,129 C98,129 90,128 83,126 C64,120 50,102 50,78 C50,48 74,26 105,26 Z" />

          {/* Casque */}
          <path className="o-tr" d="M58,60 C66,18 144,18 152,60" strokeWidth={14} />
          <path className="o-tp" d="M58,60 C66,18 144,18 152,60" strokeWidth={6.5} />
          <path className="o-f" d="M150,66 h16 a10,10 0 0 1 10,10 v20 a10,10 0 0 1 -10,10 h-16 z" />
          <path className="o-tr" d="M162,106 C160,124 145,131 131,125" strokeWidth={10} />
          <path className="o-tp" d="M162,106 C160,124 145,131 131,125" strokeWidth={4} />
          <circle className="o-f" cx={130} cy={125} r={6.5} />

          <Visage nom={p.visage} />
        </g>

        {/* Bras — tracés après la tête : une loupe ou une main au menton
            passaient sinon derrière elle. */}
        <g className={p.brasG ?? ""}>
          <path className="o-tr" d={p.bg} />
          <path className="o-tp" d={p.bg} />
          <Main x={p.mg[0]} y={p.mg[1]} r={p.mg[2]} />
        </g>
        <g className={p.brasD ?? ""}>
          <path className="o-tr" d={p.bd} />
          <path className="o-tp" d={p.bd} />
          <Main x={p.md[0]} y={p.md[1]} r={p.md[2]} pouce={p.pouceD} outil={p.main} />
        </g>

        {p.signe && <Signe nom={p.signe} />}
      </g>
    </svg>
  );
}

export const Operateur = memo(OperateurBrut);
