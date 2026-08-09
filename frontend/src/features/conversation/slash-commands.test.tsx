import { describe, expect, it } from "vitest";
import { matchSlashCommands, SLASH_COMMANDS } from "./slash-commands";

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
});
