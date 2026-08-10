import type { Metadata } from "next";
import { Chakra_Petch, Barlow, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

/* Three type roles, deliberately paired — and, unlike the previous config,
 * actually loaded. The old setup declared JetBrains Mono in tailwind.config
 * without ever loading it, so every `font-mono` reading in the cockpit
 * silently rendered in whatever monospace the OS happened to supply.
 *
 * Chakra Petch — display. Squared terminals and clipped corners: an
 *   instrument face, not a web headline. Used for numerals, screen titles
 *   and the wordmark, where type should feel stamped rather than typed.
 * Barlow — interface. A grotesk drawn from signage and transport lettering;
 *   slightly narrow, so dense operational labelling stays legible.
 * IBM Plex Mono — data. Every ID, telemetry value and code block. Chosen
 *   over the usual JetBrains/Fira default for its narrower figures and
 *   genuinely distinguishable 0/O and 1/l. */
const chakra = Chakra_Petch({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-chakra",
  display: "swap",
});

const barlow = Barlow({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-barlow",
  display: "swap",
});

const plex = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Hermes OS — Mission Control",
  description: "Operations cockpit for autonomous local AI agents.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`dark ${chakra.variable} ${barlow.variable} ${plex.variable}`}>
      <body>
        <Providers>{children}</Providers>
        {/* Surface, above the app and inert to the pointer. Large flat
            panels read as sterile vector fills without it; real instruments
            have grain and fall off toward the edges. */}
        <div className="room-vignette" aria-hidden="true" />
        <div className="room-grain" aria-hidden="true" />
      </body>
    </html>
  );
}
