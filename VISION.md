# Hermes OS — Vision

> *Un système d'exploitation pour agents IA, pas un simple assistant.*

## Philosophy

Hermes OS is not a chatbot. It is an **operating system for autonomous AI agents** — a modular, extensible runtime designed to orchestrate, execute, and govern multi-step missions across heterogeneous AI backends.

The name "OS" is deliberate. Just as a computer operating system manages processes, memory, devices, and scheduling, Hermes OS manages:

- **Runtimes** — abstracted AI backends (Ollama, OpenAI, Anthropic, vLLM…)
- **Agents** — transient or persistent worker processes
- **Memory** — structured, scoped, and queryable
- **Execution** — DAG-based task orchestration with recovery
- **Events** — a central bus connecting all subsystems

## Goals

1. **Backend-agnostic AI execution** — swap Ollama for OpenAI or Claude by changing configuration, not code.
2. **Deterministic task orchestration** — every mission is a validated DAG with retry, fallback, and recovery.
3. **Observability by design** — every subsystem publishes events to a central bus.
4. **Extensibility without modification** — new runtimes, skills, memory backends, and integrations are pluggable.
5. **Local-first, cloud-ready** — designed for local hardware (RX 6800 / i5-13500 / 32 GB) but structured for cloud deployment.

## Architecture Principles

- **Separation of concerns** — RAL, Agent Layer, Memory Layer, Event Layer, Service Layer. Each has one job.
- **Dependency injection** — no global singletons (except the legacy SDS EventBus holder). Every dependency is injected.
- **Protocols over inheritance** — `RuntimeInterface` is a Protocol. Any object that ducks it is a runtime.
- **Tests without network** — every module is testable with in-memory stubs. No real backend required.
- **Progressive complexity** — start with `StubRuntime`, graduate to `OllamaClient`, then OpenAI, Anthropic, vLLM.

## What Makes Hermes OS Different

| Dimension | Traditional AI Assistant | Hermes OS |
|---|---|---|
| Runtime | Single model | Pluggable, selectable, swappable |
| Execution | Stateless chat | DAG-based, recoverable missions |
| Memory | Ephemeral context | Scoped, persistent, queryable |
| Agents | Monolithic | Specialised, orchestratable |
| Fallback | None | Automatic, circuit breaker |
| Observability | Logs | Structured events, metrics |
| Policies | None | Rule-based runtime governance |

## Long-Term Vision

Hermes OS aims to become the **Linux kernel of AI agent orchestration** — a foundation layer that:

1. Runs **any model** through a unified runtime interface
2. Orchestrates **any task** through a standard execution graph
3. Integrates **any tool** through a skill repository
4. Remembers **any context** through a unified memory layer
5. Connects **any system** through an adapter framework

The project is structured as a series of incremental HOS (Hermes OS Specification) milestones, each adding a layer of capability without breaking the foundation.
