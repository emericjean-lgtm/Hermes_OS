import { NextResponse, type NextRequest } from "next/server";

/**
 * Retirer l'en-tête `Origin` des requêtes proxifiées vers ComfyUI
 * (HOS-194).
 *
 * ## Le défaut exact
 *
 * ComfyUI installe `origin_only_middleware` (`server.py:159`) qui compare
 * l'en-tête `Host` à l'en-tête `Origin` et renvoie **403** quand les deux
 * diffèrent. C'est une protection contre un site tiers qui ferait
 * exécuter un workflow en postant sur 127.0.0.1 depuis le navigateur de
 * l'utilisateur.
 *
 * La réécriture de `next.config.ts` envoie `Host: 127.0.0.1:8188` mais
 * **retransmet** l'`Origin` du navigateur, `http://localhost:3010`. Les
 * deux diffèrent, donc 403.
 *
 * Et c'est un 403 sélectif, ce qui l'a rendu long à voir : les feuilles
 * de style passaient — le navigateur n'envoie pas d'`Origin` pour
 * celles-là — tandis que les scripts `type="module"`, qui sont des
 * requêtes CORS, échouaient. La page se chargeait donc, affichait son
 * écran de démarrage, et n'en sortait jamais.
 *
 * ## Pourquoi retirer plutôt qu'autoriser
 *
 * L'alternative était `--enable-cors-header` côté ComfyUI. Vérifié : ce
 * drapeau **remplace** le garde au lieu de le restreindre, et une origine
 * quelconque obtient alors 200. On préfère ne rien désarmer : ici la
 * requête part du serveur Next, sans `Origin`, exactement comme un `curl`
 * — cas que le garde laisse passer par construction, puisqu'il n'a rien à
 * comparer.
 *
 * `Sec-Fetch-Site` part aussi : le même garde renvoie 403 sur
 * `cross-site`, et cet en-tête décrit la relation du **navigateur** avec
 * une origine qui n'est plus celle du serveur une fois la requête
 * réécrite.
 */
export function middleware(requete: NextRequest) {
  const entetes = new Headers(requete.headers);
  entetes.delete("origin");
  entetes.delete("sec-fetch-site");
  return NextResponse.next({ request: { headers: entetes } });
}

export const config = {
  // Uniquement le chemin proxifié : aucune raison de toucher aux
  // requêtes du Cockpit lui-même, dont l'`Origin` est légitime.
  matcher: "/comfy/:chemin*",
};
