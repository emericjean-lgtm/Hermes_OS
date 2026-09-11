# HERMES OS — CLAUDE CODE PROMPT PROTOCOL

> Standard used by ChatGPT when generating prompts for Claude Code for Hermes OS.
> The protocol combines the Hermes OS execution discipline with current Anthropic guidance for agentic coding.
>
> Target runtime: **Claude Code + Claude Opus + operator-selected high effort**.
> The prompt must optimize the work performed by the agent, not merely the prose returned by the agent.

## 1. Purpose

Every Hermes OS Claude Code prompt must be designed to maximize the probability that one autonomous pass produces a correct, integrated, verified and committed result, while minimizing follow-up prompts, scope drift, fake green tests and unnecessary architecture.

The prompt is a **task contract**, not a conversation starter.

It must tell Claude:
- what is currently true;
- exactly which chantier is active;
- what success means;
- what evidence is required;
- what must not change;
- what to inspect before editing;
- what constitutes a real end-to-end path;
- how to handle discoveries during execution;
- what must be reported at the end;
- what the next chantier is.

## 2. Evidence base and prompt-design principles

Anthropic's current guidance supports clear and direct instructions, explicit success criteria, sequential structure when order matters, structured XML tags for complex prompts, explicit action requests, and exploration/plan/code/commit workflows. Anthropic also recommends validating real behavior instead of relying only on tests and using persistent project instructions for recurring rules. [Sources listed at the end.]

For current Opus models, avoid indiscriminate over-prompting. Opus is already strong at self-correction and verification; therefore Hermes prompts should specify **what evidence must exist**, rather than mechanically demanding several redundant re-check passes or artificial self-critique loops.

For subagents, allow delegation only when it provides a real benefit: independent workstreams, isolated context, or genuinely parallel investigation. Do not force subagents for simple search, single-file changes or sequential work where maintaining local context is more effective.

## 3. Mandatory prompt architecture

Every generated Claude Code prompt should follow this structure, with XML sections because the task mixes context, constraints, evidence and instructions.

```text
<role>
<state>
<objective>
<scope>
<non_goals>
<known_evidence>
<required_inspection>
<execution_contract>
<acceptance_criteria>
<mutation_and_adversarial_tests>
<integration_and_runtime_proof>
<documentation_and_git>
<final_report>
<next_chantier>
```

Do not mechanically repeat every section when a section has no useful content, but preserve the semantic order.

## 4. Role block

State the role in one short paragraph.

Preferred pattern:

> Tu es l'agent d'implémentation senior de ce chantier Hermes OS. Tu travailles dans le dépôt réel, lis d'abord les sources de vérité indiquées, mesures avant de conclure, modifies uniquement ce qui est nécessaire, puis démontres le résultat sur le chemin réel.

The role is not a theatrical persona. It exists to anchor behavior and standards.

## 5. State block

Always provide the minimum state needed to avoid rediscovery errors.

Include when known:
- active chantier and exact number;
- current status;
- baseline commit;
- immediately relevant prior fixes;
- known open gaps that must not become accidental scope;
- next mandatory chantier.

Do not paste the entire project history unless the task genuinely needs it. Point Claude at canonical files and let it inspect them.

## 6. Objective block

Write one unambiguous objective sentence, then one paragraph explaining the reason.

The objective must describe the desired system behavior, not merely a file edit.

Bad:
> Modifier `foo.py`.

Good:
> Fermer A-10 : reconnaître le format réel des secrets OpenRouter sur les chemins `chat` et `chat_events`, sans créer de second scanner ni introduire de faux positifs, puis démontrer le refus avant émission réseau.

## 7. Scope block

Scope is a hard boundary.

State:
- allowed subsystem boundaries;
- files or directories that are likely relevant, but do not pretend they are certain before inspection;
- fixes directly necessary to complete the active chantier;
- explicitly deferred gaps.

Rule:

> Absorb corrections that are directly necessary to make the active chantier correct. Record unrelated discoveries as gaps and do not turn them into new work.

Claude must not silently widen the task because it sees adjacent cleanup opportunities.

## 8. Non-goals block

List only the few exclusions that protect the task from known failure modes.

Typical Hermes OS exclusions:
- no second authority when an existing authority exists;
- no invented compatibility layer;
- no unrelated refactor;
- no migration of user data;
- no mutation of `data/db/hermes.db` unless the active task explicitly requires it;
- no real secrets;
- no hard-coded values merely to satisfy tests;
- no broad cleanup disguised as a bug fix.

Avoid long negative lists. Prefer positive instructions where possible.

## 9. Known evidence block

Separate facts from assumptions.

Use a compact table when useful:

| Item | Evidence | Confidence |
|---|---|---|
| Current path | file/function/test reference | measured |
| Suspected root cause | runtime observation | measured / hypothesis |
| Required behavior | contract / existing test | measured |

Never present an inferred implementation detail as fact.

## 10. Required inspection block

Before coding, Claude must inspect the repository enough to validate the task against the current tree.

Required pattern:

1. Read the task-relevant canonical docs and `CLAUDE.md` / scoped rules.
2. Check `git status`, current branch and baseline relationship.
3. Locate the real producer and consumer of the behavior.
4. Trace the actual runtime path before editing.
5. Inspect existing tests and guards before adding new abstractions.
6. Identify whether an apparently missing capability is actually present elsewhere.
7. Measure surprising claims before trusting them.

This is the exploration phase recommended by Anthropic for complex Claude Code work. The prompt should tell Claude **what to establish**, not prescribe every shell command unless a particular command is required for reproducibility.

## 11. Execution contract

After inspection, Claude may implement without asking for permission merely because an implementation choice exists. Make routine judgment calls locally.

Use this ordering:

**inspect → establish baseline → implement → run focused verification → integrate → adversarial mutation → runtime/browser proof where applicable → full regression → commit/push**

When the active chantier contains a measurable contract, prefer a red-first mutation:

**baseline green → break the required invariant → expected guard/test red → fix → guard/test green → real-path demonstration**

Do not require a separate "verification phase" when Opus already verifies its work naturally. Require the evidence itself.

## 12. Acceptance criteria

Acceptance criteria must be observable and binary where possible.

For each criterion specify:
- required behavior;
- path where it must occur;
- evidence source;
- failure condition.

Prefer:

> `message → pare-feu → REFUS → aucun appel OpenRouter`

over:

> "Le pare-feu semble fonctionner correctement."

For each active chantier, define the minimum complete proof needed for `PASS`.

## 13. The Hermes OS proof ladder

Prompts must preserve the project's mandatory evidence ladder:

`PRESENT → IMPORTED → CALLED → REAL PATH → BEHAVIOR CORRECT → PERSISTENT → RESTART-SAFE → ACTUALLY USED → TESTED → DEMONSTRATED`

Claude may not stop at an earlier level and report the feature as complete.

## 14. Mutation and adversarial testing

For security, routing, verification, policy, persistence or guard tasks, require explicit adversarial contrast.

Typical mutation families:
- remove the required invariant;
- weaken the pattern or predicate;
- inject a false-positive candidate;
- bypass the expected caller;
- call through an alternate route;
- restart or reconstruct state;
- use the nearest realistic hostile boundary.

The purpose is not to create a large test suite. The purpose is to prove that the guard is actually causally connected to the defect.

Do not accept:
- skipped tests;
- xfail used to hide failure;
- opportunistic deselection;
- assertions weakened to match the broken implementation;
- artificial timeout increases whose sole purpose is to turn a failure green.

## 15. Generalization over test-fitting

Explicitly require a principled implementation when there is a risk of overfitting:

> Les tests vérifient la solution, ils ne définissent pas la solution. N'utilise pas de valeur codée en dur, de cas spécial correspondant uniquement aux tests, ni de script auxiliaire servant de contournement à une logique qui doit vivre dans le chemin de production.

Use a helper or new abstraction only when it is justified by the existing architecture or by multiple real consumers.

## 16. Resource and scope efficiency

The user deliberately uses Claude Code with Opus at high effort. Do not compensate by stuffing the prompt with artificial reasoning instructions.

Instead:
- front-load the decisive context;
- tell Claude where the source of truth lives;
- state the invariant and proof target precisely;
- let Opus reason through implementation alternatives;
- prevent scope creep explicitly;
- require concrete evidence.

Anthropic's current guidance indicates that newer Opus models can over-verify and over-expand scope when old scaffolding is too prescriptive. The protocol therefore favors **targeted verification requirements** over repeated generic "double-check everything" instructions.

## 17. Subagent policy

Claude may use subagents only where they provide clear leverage.

Good uses:
- independent repository archaeology;
- parallel analysis of unrelated subsystems;
- isolated review of a candidate implementation;
- long-running investigation that can be separated from the main context.

Avoid:
- subagents for a simple grep/read;
- subagents for a single-file change;
- forced delegation when shared state or strict sequential reasoning is required.

For Hermes OS, a subagent must never become a hidden second authority for Mission, Ledger, Aegis, verification or ResourceManager.

## 18. Browser and runtime verification

When the feature has a UI or real service path, the prompt must specify a **demonstration path**, not merely a build.

Preferred form:

> Ouvre le flux réel concerné. Déclenche l'action depuis l'interface. Vérifie les requêtes réellement émises, la réponse, l'état final et l'absence de chemin de contournement. Ne déclare pas le Center fonctionnel sur la seule base d'un composant monté ou d'un test unitaire.

For backend-only work, require the strongest available real integration probe.

## 19. Persistence and restart safety

When state is involved, explicitly distinguish:
- in-memory effect;
- persisted effect;
- restart-safe effect;
- user-visible effect.

If the feature claims persistence or restoration, the prompt must demand a restart/reload proof rather than inferring persistence from one process.

## 20. Documentation and Git

Every substantive pass must end with:
- minimal relevant documentation updates;
- clean `git diff` review;
- tests/probes in a reproducible state;
- commit on the intended branch;
- push when the existing workflow expects it.

For long-running work, Git is part of the coordination mechanism. Commit after every meaningful unit of work when the task naturally contains multiple independently recoverable units.

Do not manufacture historical narrative to fill missing changelog periods. Record real evidence only.

## 21. Final report contract

The prompt must require the following exact report order:

1. `VERDICT: 🟢 PASS / 🟠 PARTIAL / 🔴 BLOCKED / REWORK`
2. `BASELINE:`
3. `FINAL COMMIT:`
4. `ROOT CAUSE:`
5. `CHANGES:`
6. `REAL PATH:`
7. `MUTATIONS:`
8. `TESTS:`
9. `RUNTIME/BROWSER:`
10. `PERSISTENCE/RESTART:`
11. `SECURITY / DATA SAFETY:`
12. `SCOPE ABSORBED:`
13. `NEW GAPS:`
14. `ROADMAP UPDATE:`
15. `NEXT CHANTIER:` exact number and title

The final report should be concise enough to inspect quickly but complete enough for ChatGPT to audit independently.

## 22. What ChatGPT must add dynamically to each prompt

The generic protocol is not itself a task prompt. For each new chantier, ChatGPT must dynamically insert:

- the exact current chantier number from the persistent roadmap;
- the exact current status;
- the relevant baseline commit;
- the known architecture and authoritative owner;
- the actual suspected defect or missing behavior;
- the exact required real path;
- the most valuable mutations for that chantier;
- the relevant runtime/browser demonstration;
- the precise next chantier number.

Never reuse an old chantier prompt unchanged after the repository has moved.

## 23. Prompt density rule

The prompt should be **complete but not bloated**.

Include information that changes Claude's decisions. Omit narrative history that Claude can recover from the repository.

A good prompt should allow Claude to answer these questions without guessing:

- What am I changing?
- Why does it matter?
- What is already true?
- What must remain true?
- Where is the real path?
- How will I know I am actually done?
- What is forbidden scope?
- What evidence must I leave behind?
- What chantier comes next?

## 24. Prompt adaptation for Hermes OS

Hermes OS is unusual because it has repeatedly suffered from the same class of defects: correct code with no caller, decorative routes, fabricated measurements, authority duplication, tests that exercised only one path, and probes that measured the wrong thing.

Therefore every prompt should prioritize these checks whenever relevant:

**Caller check:** Is the changed function actually called by the production path?

**Authority check:** Is an existing authority being bypassed or duplicated?

**Producer/consumer check:** Does the claimed producer have a real consumer, and vice versa?

**Probe validity check:** Does the measurement instrument observe the thing it claims to measure?

**Reality check:** Does the browser/service execute the claimed path, or merely render a component?

**State check:** Does the effect survive the process boundary when persistence is part of the contract?

These checks are more valuable for Hermes OS than adding more generic ceremony to every prompt.

## 25. Required prompt style

Prompts should be:
- imperative;
- precise;
- calm;
- evidence-first;
- implementation-oriented;
- explicit about boundaries;
- explicit about acceptance criteria;
- structured with short headings/XML blocks;
- free of motivational filler;
- free of artificial chain-of-thought instructions.

Do not tell Claude to reveal hidden reasoning. Ask for decisions, evidence and concise rationale instead.

## 26. Sources used to calibrate this protocol

1. Anthropic, **Prompting best practices**, current documentation. Guidance on clarity, explicit output constraints, XML structure, long context, tool use, agentic workflows, subagent orchestration, overengineering and test-fitting.
2. Anthropic, **Claude Code Best Practices**, current engineering guidance. Guidance on explore/plan/code/commit, TDD-style workflows, specific instructions, checklists/scratchpads, and course correction.
3. Anthropic, **Prompting Claude Opus 5**, current model guidance. Guidance on task scope, over-verification, self-correction and subagent use.
4. Anthropic, **Claude Code model configuration**, current documentation. Guidance on adaptive effort and the relationship between model choice and reasoning depth.
5. Anthropic, **How Claude remembers your project**, current Claude Code documentation. Guidance on persistent instructions through `CLAUDE.md` and project-scoped rules.
6. Anthropic, **Claude Code security**, current documentation. Guidance on permission boundaries and safe operation.

## 27. Canonical rule

> **Every Claude Code prompt generated for Hermes OS must be optimized for one complete, bounded, measurable engineering pass. It must give Claude the current state, exact objective, authoritative constraints, observable acceptance criteria, real-path proof requirements and exact next chantier, while avoiding redundant reasoning ceremony and unrelated scope.**
