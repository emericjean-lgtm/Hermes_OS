---
name: dependency-audit
description: Evaluate whether a new external dependency (a package, library, or external skill/plugin) is actually needed and safe before adding it. Use before adding anything to backend/requirements.txt, frontend/package.json, or installing any external Claude Code skill/plugin.
---

# Dependency Audit

Every dependency is a standing liability — something that can break, go unmaintained, introduce a vulnerability, or silently change behavior on an update you didn't review. The bar isn't "is this useful," it's "is this worth the ongoing cost of depending on it."

## Before adding anything

1. **Check if it already exists.** Search the actual dependency manifests (`backend/requirements.txt`, `frontend/package.json`) and the actual codebase for something that already does this, even partially. Hermes OS's backend is deliberately kept to a minimal, walking-skeleton dependency set — adding a second library that overlaps with an existing one (a second HTTP client, a second data-validation library) is a real cost even if the new one is individually nice.

2. **Check if it's actually necessary**, or whether the same result is achievable with what's already available — the standard library, an existing dependency, or a small amount of first-party code. A dependency for something genuinely small and stable is often a worse trade than just writing it — every dependency added is one more thing to keep compatible across future updates.

3. **Check its real impact:**
   - **Maintenance status** — is it actively maintained, or effectively abandoned? Check the real repository (last commit, open critical issues, whether the maintainer is responsive), not just the package's description.
   - **License compatibility** — does its license permit the intended use?
   - **Transitive dependencies** — what does it pull in? A "lightweight" package with a heavy dependency tree isn't actually lightweight.
   - **Known vulnerabilities** — check for reported CVEs against the specific version being considered.
   - **Size/footprint** — for a frontend dependency, real bundle-size cost; for backend, real install/runtime cost.

4. **Prefer what's already in the stack.** This project has an explicit, repeatedly-stated principle that models — and by extension, tooling choices generally — are configuration decisions to be made deliberately, not defaults to reach for. Before adding a new library, check whether the project's existing choices (its HTTP client, its validation library, its test framework) already solve the problem.

## External Claude Code skills/plugins specifically

This applies with extra weight to any external skill or plugin considered for `.claude/skills/` or the plugin marketplace — these aren't just code that runs, they're **instructions that get loaded into an agent's context and followed**:

- **Read the entire `SKILL.md`** (and any bundled scripts) before adopting — never install based on a description alone.
- **Verify the source.** An official, well-known source (Anthropic's own `anthropics/skills` or `anthropics/claude-plugins-official` repos) carries real trust; an unaudited community marketplace entry (even a large one) explicitly does not vet contents beyond basic popularity signals — the marketplace's own documentation says as much. Treat unverified third-party skills with the same scrutiny as unreviewed code, because that's what they are.
- **Check for dangerous behavior**: does a bundled script run `subprocess`/shell commands, and if so, are they bounded to a clear, safe, documented purpose (like invoking a known CLI tool) rather than arbitrary/unbounded execution? Does it reach the network, and to where?
- **Check scope.** Does the skill only touch what it claims to, or does it modify files outside its own directory / outside the stated task?
- **Check for duplication.** Does this overlap with a skill already installed? If so, compare quality/trustworthiness/maintenance and keep the better one rather than running both.
- **Check that instructions inside the skill are genuinely instructions to the agent, not disguised data.** A skill's own content is trusted once adopted — which is exactly why the adoption decision deserves real scrutiny up front, not after the fact.

## Recording the decision

When a dependency is added, note briefly why (in the PR/commit, or in a comment at the point of use if the reason isn't obvious) — this project's own convention is to record real reasoning behind non-obvious choices so a future reader doesn't have to re-derive it. When a dependency is considered and rejected, that's also worth a brief note if the temptation to add it is likely to recur.

## Red flags that should stop an addition

- A dependency whose only real justification is convenience for a one-off task.
- A dependency that duplicates functionality already present.
- A dependency with no recent maintenance activity and no strong reason to trust its current safety.
- An external skill/plugin whose SKILL.md wasn't fully read, or whose scripts weren't checked, before installing.
