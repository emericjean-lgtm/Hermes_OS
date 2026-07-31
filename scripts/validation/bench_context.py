"""Separate a model's long-context ability from Ollama's context configuration.

The per-model benchmark showed every model failing to retrieve a fact buried in
a long document. That result is ambiguous on its own: Ollama defaults to a
modest `num_ctx`, and a prompt longer than the window is silently truncated from
the front — exactly where the fact was placed. A model cannot be blamed for text
it was never shown.

This runs the same needle-in-a-haystack probe at several `num_ctx` values and
records, for each, the prompt tokens Ollama actually evaluated. If the evaluated
token count stops growing while the prompt keeps growing, the window truncated —
a configuration limit. If the window holds the whole prompt and the answer is
still wrong, that is the model.

Strictly sequential: one model resident at a time, unloaded and VRAM verified
between models, exactly like bench_models.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, __file__.rsplit("scripts", 1)[0])
from scripts.validation.bench_models import (  # noqa: E402
    _get, _post, load_model, resident_models, unload_all, vram_in_use,
)

NEEDLE = "ZX-9137"


def haystack(target_words: int) -> str:
    """A document with the needle near the front, padded to ~target_words."""
    filler = " ".join(f"paragraph{i} contains only routine filler text"
                      for i in range(max(target_words // 6, 1)))
    return (
        f"ARCHIVE DOCUMENT. The access token is {NEEDLE}. Remember it.\n\n"
        f"{filler}\n\n"
        "Question: what is the access token stated at the top of this document? "
        "Answer with the token only."
    )


def probe(model: str, num_ctx: int, words: int, timeout: int) -> dict:
    prompt = haystack(words)
    try:
        r = _post("/api/generate", {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": num_ctx},
        }, timeout=timeout)
    except Exception as e:
        return {"num_ctx": num_ctx, "target_words": words, "ok": False,
                "error": f"{type(e).__name__}: {e}"}

    text = (r.get("response") or "").strip()
    prompt_tokens = int(r.get("prompt_eval_count", 0) or 0)
    resident = [m for m in resident_models()
                if (m.get("name") or m.get("model")) == model]
    return {
        "num_ctx": num_ctx,
        "target_words": words,
        "ok": True,
        "prompt_tokens_evaluated": prompt_tokens,
        "context_length_reported": int(resident[0].get("context_length", 0)) if resident else 0,
        "vram_bytes": int(resident[0].get("size_vram", 0)) if resident else 0,
        "found_needle": NEEDLE.lower() in text.lower(),
        "completion_tokens": int(r.get("eval_count", 0) or 0),
        "answer_head": text[:80],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="qwen3:4b,deepseek-r1:14b,hermes3-feedmail:64k")
    ap.add_argument("--contexts", default="4096,8192,32768,65536")
    ap.add_argument("--words", type=int, default=6000,
                    help="haystack size in words; must exceed the smallest window")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out", default="docs/release/bench_context.json")
    args = ap.parse_args()

    try:
        version = _get("/api/version").get("version", "?")
    except Exception as e:
        print(f"Ollama unreachable: {e}", file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    contexts = [int(c) for c in args.contexts.split(",") if c.strip()]

    print(f"Ollama {version} | needle={NEEDLE} | haystack ~{args.words} words")
    print("One model resident at a time.\n")

    out = {"started_at": datetime.now(timezone.utc).isoformat(),
           "needle": NEEDLE, "haystack_words": args.words, "models": []}

    for model in models:
        leftover, _ = unload_all()
        if leftover:
            print(f"  ! {leftover/1024**2:.0f} MiB resident before load", flush=True)

        print(f"[{model}]", flush=True)
        ok, err, load_ms = load_model(model, args.timeout)
        entry = {"model": model, "loaded": ok, "load_error": err, "probes": []}
        if not ok:
            print(f"    LOAD FAILED: {err}", flush=True)
            out["models"].append(entry)
            continue

        for ctx in contexts:
            started = time.perf_counter()
            p = probe(model, ctx, args.words, args.timeout)
            p["wall_ms"] = round((time.perf_counter() - started) * 1000, 1)
            entry["probes"].append(p)
            if p["ok"]:
                print(f"    num_ctx={ctx:6d}  prompt_tokens={p['prompt_tokens_evaluated']:6d}"
                      f"  vram={p['vram_bytes']/1024**3:5.2f} GiB"
                      f"  needle={'FOUND' if p['found_needle'] else 'missed'}"
                      f"  ({p['wall_ms']/1000:.1f}s)", flush=True)
            else:
                print(f"    num_ctx={ctx:6d}  FAILED: {p['error'][:70]}", flush=True)

        after, _ = unload_all()
        entry["vram_after_unload"] = after
        print(f"    unloaded, VRAM now {after/1024**2:.0f} MiB", flush=True)
        out["models"].append(entry)

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(flush=True)

    # A model can only be blamed for text it was actually shown. Ollama reserves
    # part of num_ctx for the completion, so the usable prompt window is smaller
    # than the setting: at num_ctx=4096 only ~2050 prompt tokens are evaluated.
    # The needle sits at the front, which is exactly what truncation drops.
    # "Model limitation" therefore requires the window to have held the *whole*
    # prompt — evaluated tokens must stop growing because the prompt ran out,
    # not because the window did.
    full_prompt_tokens = max(
        (p["prompt_tokens_evaluated"] for e in out["models"] for p in e["probes"]
         if p.get("ok")), default=0)

    print("VERDICT PER MODEL")
    for e in out["models"]:
        if not e["loaded"]:
            print(f"  {e['model']:34} not loaded")
            continue
        good = [p for p in e["probes"] if p.get("ok")]
        if not good:
            print(f"  {e['model']:34} no successful probe")
            continue
        found = [p["num_ctx"] for p in good if p["found_needle"]]
        tokens = [p["prompt_tokens_evaluated"] for p in good]
        largest = max(good, key=lambda p: p["prompt_tokens_evaluated"])
        # Did the biggest window stop short of the setting? Then it held the
        # whole prompt rather than clipping it.
        held_whole_prompt = largest["prompt_tokens_evaluated"] < (largest["num_ctx"] * 0.45)

        if found:
            e["verdict"] = f"configuration: retrieved once num_ctx>={min(found)}"
            print(f"  {e['model']:34} needle FOUND from num_ctx={min(found)} "
                  f"-> CONFIGURATION limit, not the model")
        elif not held_whole_prompt:
            e["verdict"] = "truncated at every setting; model not implicated"
            print(f"  {e['model']:34} prompt truncated at every setting "
                  f"({min(tokens)}->{max(tokens)} tok, all ~num_ctx/2) "
                  f"-> INCONCLUSIVE, raise num_ctx or shorten the document")
        else:
            e["verdict"] = "model: whole prompt evaluated, needle still missed"
            print(f"  {e['model']:34} whole prompt evaluated "
                  f"({largest['prompt_tokens_evaluated']} tok within "
                  f"num_ctx={largest['num_ctx']}) yet needle missed "
                  f"-> MODEL limitation")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"\nfull prompt is ~{full_prompt_tokens}+ tokens at "
          f"{args.words} words\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
