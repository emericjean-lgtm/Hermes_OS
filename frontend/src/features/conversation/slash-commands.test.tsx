import { describe, expect, it } from "vitest";
import { matchSlashCommands, SLASH_COMMANDS, skillsToSlashCommands } from "./slash-commands";
import type { AgentSkills } from "@/services/client";

/**
 * Assistant v2 feedback round: /help and /context were added on top of the
 * original /clean, /resume, /compact set. Both wrap real, pre-existing
 * backend endpoints (GET /conversation/sessions and
 * GET /conversation/{id}/context) that had no Cockpit caller before this.
 */

describe("SLASH_COMMANDS", () => {
  it("includes the five commands, /compact still marked unimplemented", () => {
    const cmds = SLASH_COMMANDS.map((c) => c.cmd);
    expect(cmds).toEqual(["/help", "/clean", "/resume", "/context", "/compact"]);
    expect(SLASH_COMMANDS.find((c) => c.cmd === "/compact")?.implemented).toBe(false);
    expect(SLASH_COMMANDS.filter((c) => c.cmd !== "/compact").every((c) => c.implemented)).toBe(true);
  });
});

describe("matchSlashCommands", () => {
  it("matches /help and /context by prefix", () => {
    expect(matchSlashCommands("/hel").map((c) => c.cmd)).toEqual(["/help"]);
    expect(matchSlashCommands("/con").map((c) => c.cmd)).toEqual(["/context"]);
  });

  it("returns every command for a bare slash", () => {
    expect(matchSlashCommands("/")).toHaveLength(SLASH_COMMANDS.length);
  });

  it("returns nothing once the input contains a space (no longer a command)", () => {
    expect(matchSlashCommands("/help me")).toHaveLength(0);
  });

  it("returns nothing for text that doesn't start with a slash", () => {
    expect(matchSlashCommands("help")).toHaveLength(0);
  });

  it("also matches an extra (skill) command when given one", () => {
    const skill = { cmd: "/web-search", label: "/web-search", description: "",
      icon: SLASH_COMMANDS[0].icon, implemented: true, insertText: "/web-search " };
    expect(matchSlashCommands("/web", [skill]).map((c) => c.cmd)).toEqual(["/web-search"]);
    // The static commands are still searched alongside the extra ones.
    expect(matchSlashCommands("/hel", [skill]).map((c) => c.cmd)).toEqual(["/help"]);
  });
});

/**
 * Operator request: only the 5 conversation-management commands were ever
 * offered as slash commands — the 81 skills Hermes Agent actually has
 * installed (`backend/skills/registre.py`, exposed at GET /skills/agent)
 * never were, even though the data was already fetched elsewhere (the
 * Skills Center).
 */
describe("skillsToSlashCommands", () => {
  const agentSkills: AgentSkills = {
    total: 2,
    racine: "/hermes/skills",
    correlation_impossible: "",
    domaines: [
      {
        nom: "recherche",
        competences: [
          { nom: "Web Search", description: "Chercher sur le web",
            provenance: "systeme_intacte", provenance_preuve: "" },
        ],
      },
      {
        nom: "code",
        competences: [
          { nom: "  Refactor / Clean-up  ", description: "",
            provenance: "systeme_intacte", provenance_preuve: "" },
        ],
      },
    ],
  };

  it("slugifies each skill name into a typable command", () => {
    const cmds = skillsToSlashCommands(agentSkills).map((c) => c.cmd);
    expect(cmds).toEqual(["/web-search", "/refactor-clean-up"]);
  });

  it("selecting one inserts text rather than an empty description", () => {
    const [webSearch] = skillsToSlashCommands(agentSkills);
    expect(webSearch.insertText).toBe("/web-search ");
    expect(webSearch.description).toBe("Chercher sur le web");
  });

  it("falls back to the domain name when a skill has no description", () => {
    const [, refactor] = skillsToSlashCommands(agentSkills);
    expect(refactor.description).toBe("code");
  });

  it("returns nothing when the skills haven't loaded yet", () => {
    expect(skillsToSlashCommands(undefined)).toEqual([]);
  });
});
