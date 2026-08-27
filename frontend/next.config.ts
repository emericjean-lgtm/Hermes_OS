import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["lucide-react"],

  // Sans cela, Next redirige `/comfy/` vers `/comfy` (308), et les
  // chemins RELATIFS du HTML de ComfyUI — `assets/...`, `user.css` — se
  // resolvent alors contre `/` au lieu de `/comfy/`. La page se charge,
  // aucune de ses ressources ne suit.
  skipTrailingSlashRedirect: true,

  // ComfyUI servi sous notre propre origine (HOS-194).
  //
  // Sans cela, l'iframe du Studio Center recevait **403** : ComfyUI
  // installe `origin_only_middleware` (server.py:239) qui refuse toute
  // requete dont l'en-tete `Origin` ne correspond pas au sien, et
  // localhost:3010 n'est pas 127.0.0.1:8188.
  //
  // La reecriture est faite **cote serveur** : la requete part de Next,
  // sans en-tete `Origin`, et passe donc le garde — qu'on laisse ainsi
  // intact. L'alternative, `--enable-cors-header`, aurait supprime ce
  // garde pour tout le monde : verifie, une origine quelconque obtenait
  // alors 200. On prefere ne rien desarmer.
  async rewrites() {
    return [
      { source: "/comfy", destination: "http://127.0.0.1:8188/" },
      { source: "/comfy/:chemin*", destination: "http://127.0.0.1:8188/:chemin*" },
    ];
  },
};

export default nextConfig;
