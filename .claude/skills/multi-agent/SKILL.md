---
name: multi-agent
description: Parallelize genuinely independent parts of a larger task across multiple subagents — e.g. backend + frontend + tests + docs for one feature. Use when a task naturally decomposes into pieces with no dependency between them; never for pieces that share files or depend on each other's output.
---

# Multi-Agent Development

Parallelism is a tool for genuinely independent work, not a default. The moment two pieces of work touch the same file or one needs the other's output to start, running them concurrently doesn't save time — it creates a merge conflict or a race, and you spend more time reconciling than you saved.

## When it's a real fit

A feature that decomposes into pieces with no real dependency between them:

```
Feature HOS
├── Backend    (new endpoint/logic)
├── Frontend   (new UI consuming it)
├── Tests      (for the backend logic)
└── Documentation
```

This looks parallelizable, but check each pair before assuming it is: frontend work that needs the backend's real response shape to build against isn't independent of backend — it depends on an interface being *decided*, even if not yet implemented. If the interface is settled (a spec, a type definition, an agreed contract) before starting, frontend and backend can genuinely run concurrently against that agreed shape. If the interface is still being figured out as backend is built, they're not independent yet — decide the contract first, then parallelize.

## Rules

- **Never parallelize dependent tasks.** If task B needs task A's actual output (not just its planned shape) to start, they're sequential — running them concurrently produces broken speculative work.
- **Never let two agents modify the same file concurrently.** Even independent-seeming logic in a shared file creates a real merge conflict. If two pieces of work would touch the same file, either sequence them or split the file's concerns first.
- **Use worktrees when genuinely needed** — for changes large/risky enough that isolated working directories are worth the overhead. For small parallel pieces, plain independent file scopes are usually enough; reach for worktrees when the parallel work is substantial or long-running enough that cross-contamination risk is real.
- **Always integrate and test the combined result before calling it done.** Each piece passing its own isolated check doesn't guarantee the pieces work together — run the full relevant test suite (see [hermes/verification](../hermes/verification/SKILL.md)) against the merged result, not just each piece independently.
- **Always do a final review across the whole change**, not per-piece in isolation — an architecture-level issue (see [architecture-review](../architecture-review/SKILL.md)) often only becomes visible once you see how the pieces actually fit together.

## Deciding what's actually independent

Before splitting work across agents, map real dependencies explicitly (see [implementation-planning](../implementation-planning/SKILL.md)) — don't just assume a task tree that *looks* parallel (backend/frontend/tests/docs, one branch each) is actually free of cross-dependency. Common false-independence traps:
- Tests written against an interface that ends up changing once the implementation is actually built.
- Documentation written from a plan that the implementation later deviates from.
- Two "independent" backend changes that both modify the same shared registry, config file, or central contract.

## Briefing each agent

Each agent starts cold — it has no memory of the parent task's context. A brief needs: what the overall feature is and why, exactly what this agent's slice covers (and explicitly what it does *not* cover, to prevent scope bleed into another agent's piece), the interface/contract it should build against if it depends on a not-yet-built piece, and what "done" looks like for its slice specifically (tests passing, a specific behavior verified).

## After parallel work completes

1. Integrate all pieces into one coherent change.
2. Run the full test suite on the integrated result — not each piece's own tests in isolation.
3. Do one holistic review pass (see [code-review](../code-review/SKILL.md) and [architecture-review](../architecture-review/SKILL.md)) as if the combined diff were written by one person, checking specifically for integration seams (does the frontend's assumed response shape match what the backend actually returns? Do the tests exercise the real integrated path or just each piece's mocked version?).
4. Only then consider the feature complete — a set of individually-passing pieces is not the same as a working integrated feature.
