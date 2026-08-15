<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!--
  Ce qui précède est un bloc géré par l'outillage Next (voir les marqueurs
  BEGIN/END). Ne pas le modifier : une régénération l'écraserait, et la
  correction disparaîtrait sans bruit. D'où cette note à côté plutôt que
  dedans.
-->

## Le chemin ci-dessus n'existe pas dans cette installation

`node_modules/next/dist/docs/` est **absent** — vérifié le 2026-08-15 sur
Next 15.1.0, qui ne livre pas de documentation dans son paquet. La
consigne est donc insuivable telle quelle, ce qui est pire qu'une consigne
absente : elle apprend à passer outre.

L'avertissement, lui, reste juste. Next **15.1.0** et React **19**
(versions exactes dans `package.json`) portent de vraies ruptures d'API.
N'écris pas de code frontend depuis tes souvenirs.

### Où vérifier, par ordre d'autorité

1. **`node_modules/next/*.d.ts` et `node_modules/@types/react/`** — la
   surface d'API réellement installée. Un typage ne se trompe pas de
   version, contrairement à un souvenir ou à un article de blog.
   `npx tsc --noEmit` a le dernier mot.
2. **`src/` lui-même** — pour les conventions de ce dépôt : structure des
   Centers, hooks TanStack Query, primitives `@/components/ui/card`,
   scaffolding `@/components/center-scaffold`. Un composant existant vaut
   mieux qu'une règle écrite, parce qu'il est compilé et testé à chaque
   exécution.
3. **`node_modules/next/README.md`**, à défaut.

### Pourquoi rien n'est énuméré ici

Aucune liste des ruptures de Next 15 ou React 19 ne figure dans ce
fichier, délibérément : écrite de mémoire, elle aurait exactement le
défaut contre lequel le bloc ci-dessus met en garde, et elle vieillirait
sans que personne le remarque. « Est-ce que cette API existe encore, avec
cette signature ? » se demande au typage installé, jamais à un document.

### Les commandes qui tranchent

```bash
npx tsc --noEmit     # la seule autorité sur ce qui compile
npx vitest run       # 92 tests
```

Backend et frontend se lancent par `preview_start` (`.claude/launch.json`),
jamais par un `npm run dev` détaché.
