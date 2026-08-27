import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * L'incident : « je change d'onglet et ça ne fonctionne pas » (HOS-198).
 *
 * Trois fois de suite, la bascule de Center s'est cassée au même endroit —
 * `AnimatePresence` autour du conteneur de vue — et de trois façons
 * différentes :
 *
 * 1. `mode="wait"` bloquait le montage de la vue suivante tant que la
 *    sortie de la précédente n'était pas confirmée terminée. Rien ne
 *    garantit qu'elle le soit : une frame de composition manquée suffit.
 * 2. Sans `mode` mais avec `exit`, l'ancienne vue restait affichée
 *    par-dessus la nouvelle pendant le fondu — visible surtout quand elle
 *    contenait l'iframe ComfyUI, qui ignore le fondu de ses ancêtres.
 * 3. Sans `exit`, `AnimatePresence` ne relâchait plus jamais l'enfant
 *    sortant. Chaque navigation empilait un Center de plus dans le DOM,
 *    tous à opacité 1 ; le premier gardait le haut de la page et les
 *    suivants étaient poussés hors écran. Mesuré sur l'application en
 *    marche : Studio, puis Assistant, puis Mission Center, empilés.
 *
 * ## Pourquoi ce test lit le source au lieu de rendre le shell
 *
 * Parce que la version qui rendait le shell a été écrite, et qu'elle **ne
 * servait à rien**. Vérifiée comme doit l'être tout garde-fou : la faute a
 * été réintroduite exprès (`AnimatePresence` remis autour du conteneur de
 * vue), et les trois tests de rendu sont restés **verts**. Sous JSDOM, il
 * n'y a pas de vraies frames de composition ; framer-motion y relâche
 * l'enfant sortant immédiatement, et le défaut — qui est précisément une
 * sortie qui ne se termine jamais — ne peut pas s'y produire.
 *
 * Garder ces tests aurait été pire que de n'en avoir aucun : ils auraient
 * affirmé garder une régression qu'ils laissent passer. Le comportement
 * réel a donc été vérifié dans un vrai navigateur (32 combinaisons de
 * sous-onglet Studio × onglet principal, iframe ComfyUI comprise, zéro
 * échec, un seul `.center-enter` en DOM à chaque pas), et ce qui reste ici
 * est ce qui *peut* se garder automatiquement : que la construction fautive
 * n'a pas été remise.
 *
 * C'est un garde-fou structurel, comme
 * `backend/tests/test_hermes_agent_is_the_brain.py` : il ne prouve pas que
 * la navigation marche, il empêche le retour de la cause connue.
 */

const SHELL = readFileSync(
  join(__dirname, "cockpit-shell.tsx"),
  "utf-8",
);

/** Le corps de `CockpitShell`, commentaires retirés — le fichier explique
 *  longuement pourquoi `AnimatePresence` en est absent, et un test qui
 *  lirait ces explications comme du code se déclencherait sur sa propre
 *  documentation. */
const CODE = SHELL
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/\/\/[^\n]*/g, "");

describe("Bascule de Center (HOS-198)", () => {
  it("n'enveloppe pas le conteneur de vue dans AnimatePresence", () => {
    // Le message porte la raison : un échec doit apprendre pourquoi, pas
    // seulement qu'une chaîne est présente.
    expect(
      CODE,
      "AnimatePresence est revenu autour du conteneur de vue. C'est la " +
        "cause des trois pannes de navigation de HOS-196/198 : il ne " +
        "relâche l'ancienne vue qu'une fois la sortie confirmée terminée, " +
        "confirmation qui dépend d'une frame de composition et peut ne " +
        "jamais venir. L'entrée est une animation CSS (`center-enter`) que " +
        "le remontage déclenche seul ; un `key` sur un élément ordinaire " +
        "suffit et démonte de façon déterministe.",
    ).not.toContain("AnimatePresence");
  });

  it("monte la vue sur un `key` porté par l'onglet actif", () => {
    // C'est ce `key` qui fait tout le travail de démontage désormais :
    // sans lui, React réutiliserait le même élément d'une vue à l'autre et
    // `center-enter` ne rejouerait jamais.
    expect(CODE).toContain("key={activeView}");
  });

  it("garde le conteneur de vue borné pour le seul Assistant", () => {
    // L'autre moitié de HOS-196 : `h-full overflow-hidden` appliqué à tous
    // les Centers rognait le contenu de dix-sept d'entre eux, qui n'ont pas
    // de défilement interne et dépendent du débordement vers le conteneur
    // parent. Le couple reste réservé à l'Assistant, seul Center à gérer
    // son propre défilement.
    expect(CODE).toContain("h-full relative overflow-hidden center-enter");
    expect(CODE).toContain("min-h-full relative center-enter");
  });
});
