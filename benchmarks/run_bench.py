"""Benchmark the anonymization on benchmarks/dataset.jsonl and write benchmarks/results.md.

1. Detection quality of Presidio, as the pii-fr guardrail runs it (same entities, score threshold and overlap
   merging, all read from config/litellm.yaml), against local LLMs asked to list the personal data of each text.
2. Latency added by the guardrail: the gateway with and without pii-fr, on the same texts, with mock answers so that
   no model time hides the difference.

Run with `just gateway-bench` (starts the stack first). `--skip-llm` keeps only Presidio and the latency part.
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "guardrails"))
from presidio_markers import merge_overlaps  # noqa: E402  (the guardrail's own overlap merging)

load_dotenv(ROOT / ".env")
GATEWAY_URL = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
ANALYZER_URL = f"http://localhost:{os.environ.get('PRESIDIO_ANALYZER_PORT', '5002')}"
OLLAMA_URL = f"http://localhost:{os.environ.get('OLLAMA_PORT', '11435')}"
MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]

DATASET = Path(__file__).with_name("dataset.jsonl")
RESULTS = Path(__file__).with_name("results.md")
# Model name in Ollama -> gateway alias whose internal price applies (config/litellm.yaml).
LLMS = {"qwen2.5:0.5b": "chat-small", "qwen2.5:1.5b": "chat-large", "qwen2.5:7b": None}
LATENCY_ROUNDS = 3
# Small models sometimes loop in JSON mode until the context is full; a real answer fits well within this.
MAX_ANSWER_TOKENS = 768

LLM_PROMPT = """Tu détectes les données personnelles dans un texte français.
Réponds uniquement avec un objet JSON de la forme {{"entities": [{{"type": "...", "text": "..."}}]}}.
"text" doit être recopié exactement tel qu'il apparaît dans le texte.
Types possibles :
{types}
Ne relève pas les dates, les montants, les numéros de dossier ni les noms d'entreprise.
Si le texte ne contient aucune donnée personnelle, réponds {{"entities": []}}."""

TYPE_DESCRIPTIONS = {
    "PERSON": "nom ou prénom d'une personne",
    "LOCATION": "ville ou pays, hors adresse complète",
    "FR_ADDRESS": "adresse postale (numéro et voie, avec code postal et ville s'ils suivent)",
    "EMAIL_ADDRESS": "adresse e-mail",
    "PHONE_NUMBER": "numéro de téléphone",
    "IBAN_CODE": "IBAN",
    "CREDIT_CARD": "numéro de carte bancaire",
    "CRYPTO": "adresse de portefeuille de cryptomonnaie",
    "IP_ADDRESS": "adresse IP",
    "FR_NIR": "numéro de sécurité sociale",
    "FR_FISCAL_NUMBER": "numéro fiscal",
}


# --- Inputs ---------------------------------------------------------------------------------------------------


def load_dataset() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines()]


def gateway_settings() -> tuple[list[str], float, dict[str, tuple[float, float]]]:
    """Entities and score threshold of the pii-fr guardrail, and the internal price of each alias."""
    config = yaml.safe_load((ROOT / "config" / "litellm.yaml").read_text())
    guardrail = next(g for g in config["guardrails"] if g["guardrail_name"] == "pii-fr")["litellm_params"]
    entities = list(guardrail["pii_entities_config"])
    threshold = guardrail["presidio_score_thresholds"]["ALL"]
    prices = {
        m["model_name"]: (m["litellm_params"].get("input_cost_per_token", 0), m["litellm_params"].get("output_cost_per_token", 0))
        for m in config["model_list"]
    }
    return entities, threshold, prices


# --- Detectors: each returns spans {"type", "start", "end"}, merged as the guardrail merges them ---------------


def presidio(client: httpx.Client, text: str, entities: list[str], threshold: float) -> list[dict]:
    response = client.post(
        f"{ANALYZER_URL}/analyze",
        json={"text": text, "language": "fr", "entities": entities, "score_threshold": threshold},
    )
    response.raise_for_status()
    found = [{"entity_type": r["entity_type"], "start": r["start"], "end": r["end"], "score": r["score"]} for r in response.json()]
    return [{"type": r["entity_type"], "start": r["start"], "end": r["end"]} for r in merge_overlaps(found)]


def locate(text: str, value: str) -> list[tuple[int, int]]:
    """Every position of value in text, exact first, then ignoring case."""
    for haystack, needle in ((text, value), (text.casefold(), value.casefold())):
        spans, start = [], haystack.find(needle)
        while needle and start != -1:
            spans.append((start, start + len(needle)))
            start = haystack.find(needle, start + 1)
        if spans:
            return spans
    return []


def llm(client: httpx.Client, model: str, text: str, entities: list[str]) -> tuple[list[dict], dict]:
    types = "\n".join(f"- {t} : {TYPE_DESCRIPTIONS[t]}" for t in entities)
    response = client.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": LLM_PROMPT.format(types=types)},
                {"role": "user", "content": text},
            ],
            "format": "json",
            "stream": False,
            "keep_alive": "15m",
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": MAX_ANSWER_TOKENS},
        },
    )
    stats = {"prompt_tokens": 0, "completion_tokens": 0, "invalid": 0, "not_in_text": 0}
    if response.status_code != 200:
        # Counted as a detector failure: nothing is masked, the benchmark goes on.
        stats["invalid"] = 1
        return [], stats
    body = response.json()
    stats["prompt_tokens"] = body.get("prompt_eval_count", 0)
    stats["completion_tokens"] = body.get("eval_count", 0)
    if body.get("done_reason") == "length":
        # Cut at MAX_ANSWER_TOKENS: the JSON is incomplete.
        stats["invalid"] = 1
        return [], stats
    try:
        items = json.loads(body["message"]["content"])["entities"]
        items = [item for item in items if isinstance(item, dict)]
    except (json.JSONDecodeError, KeyError, TypeError):
        stats["invalid"] = 1
        return [], stats

    found = []
    for item in items:
        entity_type, value = str(item.get("type", "")), str(item.get("text", "")).strip()
        if entity_type not in entities or not value:
            continue
        spans = locate(text, value)
        if not spans:
            # Invented or reworded: masks nothing, counts as a false positive.
            stats["not_in_text"] += 1
            found.append({"entity_type": entity_type, "start": -1, "end": -1, "score": 1.0})
        found += [{"entity_type": entity_type, "start": s, "end": e, "score": 1.0} for s, e in spans]
    located = [r for r in found if r["start"] >= 0]
    unlocated = [{"type": r["entity_type"], "start": -1, "end": -1} for r in found if r["start"] < 0]
    merged = [{"type": r["entity_type"], "start": r["start"], "end": r["end"]} for r in merge_overlaps(located)]
    return merged + unlocated, stats


# --- Scoring --------------------------------------------------------------------------------------------------


def overlap(a: dict, b: dict) -> bool:
    return a["start"] < b["end"] and b["start"] < a["end"]


def score(rows: list[dict], predictions: list[list[dict]], entities: list[str]) -> dict:
    """Type-aware precision and recall (a span counts when it overlaps one of the same type), and the share of
    personal data left with no character in clear, whatever the type found (what the guardrail really needs)."""
    per_type = {t: {"gold": 0, "found": 0, "predicted": 0, "correct": 0} for t in entities}
    masked, leaks = 0, []
    for row, predicted in zip(rows, predictions, strict=True):
        gold = [{"type": e["type"], "start": e["start"], "end": e["end"]} for e in row["entities"]]
        covered = set()
        for p in predicted:
            covered.update(range(p["start"], p["end"]))
            if p["type"] in per_type:
                per_type[p["type"]]["predicted"] += 1
                per_type[p["type"]]["correct"] += any(g["type"] == p["type"] and overlap(g, p) for g in gold)
        for g in gold:
            per_type[g["type"]]["gold"] += 1
            per_type[g["type"]]["found"] += any(p["type"] == g["type"] and overlap(g, p) for p in predicted)
            chars = [i for i in range(g["start"], g["end"]) if not row["text"][i].isspace()]
            if all(i in covered for i in chars):
                masked += 1
            else:
                leaks.append((row["id"], g["type"], row["text"][g["start"] : g["end"]]))
    totals = {k: sum(t[k] for t in per_type.values()) for k in ("gold", "found", "predicted", "correct")}
    precision = totals["correct"] / totals["predicted"] if totals["predicted"] else 0.0
    recall = totals["found"] / totals["gold"]
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"per_type": per_type, "precision": precision, "recall": recall, "f1": f1,
            "masked": masked / totals["gold"], "leaks": leaks}


def percentiles(values: list[float]) -> tuple[float, float]:
    return statistics.median(values), statistics.quantiles(values, n=20)[18]


# --- Runs -----------------------------------------------------------------------------------------------------


def run_detector(name: str, rows: list[dict], detect) -> dict:
    predictions, seconds, stats = [], [], []
    for i, row in enumerate(rows, 1):
        start = time.perf_counter()
        predicted, row_stats = detect(row["text"])
        seconds.append(time.perf_counter() - start)
        predictions.append(predicted)
        stats.append(row_stats)
        print(f"\r{name}: {i}/{len(rows)}", end="", flush=True)
    print()
    return {"predictions": predictions, "seconds": seconds, "stats": stats}


def warm_up(client: httpx.Client, model: str) -> None:
    """Load the model before timing, and download it on first use (qwen2.5:7b is not in OLLAMA_MODELS)."""
    names = [m["name"] for m in client.get(f"{OLLAMA_URL}/api/tags").json()["models"]]
    if model not in names:
        print(f"Downloading {model} into the ollama volume...")
        client.post(f"{OLLAMA_URL}/api/pull", json={"model": model, "stream": False}, timeout=3600).raise_for_status()
    client.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "prompt": "ok", "keep_alive": "15m"}).raise_for_status()


def gateway_latency(rows: list[dict]) -> dict[str, list[float]]:
    """Per-request latency of the gateway for a team with and without pii-fr, on mock answers (no model call)."""
    admin = httpx.Client(base_url=GATEWAY_URL, headers={"Authorization": f"Bearer {MASTER_KEY}"}, timeout=60)
    teams = {"without guardrail": ("bench-off", ["pii-fr"]), "with pii-fr": ("bench-on", [])}
    keys = {}
    try:
        for label, (team_id, opted_out) in teams.items():
            admin.post("/team/new", json={"team_id": team_id, "models": ["chat-small"],
                                          "metadata": {"opted_out_global_guardrails": opted_out}}).raise_for_status()
            keys[label] = admin.post("/key/generate", json={"team_id": team_id}).json()["key"]
        timings: dict[str, list[float]] = {label: [] for label in teams}
        for _ in range(LATENCY_ROUNDS):
            for label, key in keys.items():
                with httpx.Client(base_url=GATEWAY_URL, headers={"Authorization": f"Bearer {key}"}, timeout=60) as c:
                    for row in rows:
                        start = time.perf_counter()
                        c.post("/v1/chat/completions", json={
                            "model": "chat-small", "mock_response": "ok",
                            "messages": [{"role": "user", "content": row["text"]}],
                        }).raise_for_status()
                        timings[label].append((time.perf_counter() - start) * 1000)
        return timings
    finally:
        admin.post("/team/delete", json={"team_ids": [team_id for team_id, _ in teams.values()]})


# --- Report ---------------------------------------------------------------------------------------------------


def cpu_name() -> str:
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown CPU"


def pct(value: float) -> str:
    return f"{value * 100:.1f} %"


def report(rows, entities, threshold, prices, detectors: dict[str, dict], latency: dict[str, list[float]]) -> str:
    gold_counts = {t: sum(e["type"] == t for r in rows for e in r["entities"]) for t in entities}
    total = sum(gold_counts.values())
    lines = [
        "# Anonymization benchmark",
        "",
        f"Generated by `just gateway-bench` on {date.today().isoformat()}, {cpu_name()}, {os.cpu_count()} threads, "
        "CPU only. Do not edit by hand: rerun the command.",
        "",
        f"Dataset: [`dataset.jsonl`](dataset.jsonl), {len(rows)} synthetic French texts (letters, emails, messages, "
        f"forms) with {total} personal data items, generated by [`generate_dataset.py`](generate_dataset.py).",
        f"Presidio runs as the `pii-fr` guardrail does: the {len(entities)} entity types of `config/litellm.yaml`, "
        f"score threshold {threshold}, overlapping detections merged. The LLMs get the same types in a prompt and "
        "answer in JSON through Ollama, temperature 0; their spans are merged the same way.",
        "",
        "## Detection",
        "",
        "| Detector | Precision | Recall | F1 | Fully masked | Latency p50 / p95 per text | Internal price per 1,000 texts |",
        "| -- | -- | -- | -- | -- | -- | -- |",
    ]
    for name, d in detectors.items():
        s = d["score"]
        p50, p95 = percentiles([x * 1000 for x in d["seconds"]])
        if d.get("alias"):
            price_in, price_out = prices[d["alias"]]
            cost = sum(st["prompt_tokens"] * price_in + st["completion_tokens"] * price_out for st in d["stats"])
            price = f"${cost * 1000 / len(rows):.2f} (`{d['alias']}` rate)"
        elif d.get("llm"):
            price = "no internal price (not a gateway alias)"
        else:
            price = "no model call"
        lines.append(f"| {name} | {pct(s['precision'])} | {pct(s['recall'])} | {pct(s['f1'])} | {pct(s['masked'])} "
                     f"| {p50:,.0f} ms / {p95:,.0f} ms | {price} |")
    lines += [
        "",
        "- **Precision / recall**: a detected span counts when it overlaps an annotated item of the same type.",
        "- **Fully masked**: share of annotated items with no character left in clear, whatever the type detected. "
        "This is what protects the data: an address masked as a LOCATION still reaches the model as a marker.",
    ]
    llm_notes = []
    for name, d in detectors.items():
        if d.get("llm"):
            invalid = sum(st["invalid"] for st in d["stats"])
            invented = sum(st["not_in_text"] for st in d["stats"])
            tokens = sum(st["prompt_tokens"] + st["completion_tokens"] for st in d["stats"]) / len(rows)
            llm_notes.append(f"- **{name}**: {tokens:,.0f} tokens per text; {invalid} answers were unusable (invalid or cut JSON, server error); "
                             f"{invented} items returned were not in the text (reworded or invented).")
    lines += llm_notes

    lines += ["", "## Recall / precision per entity type", ""]
    header = "| Type | Items | " + " | ".join(detectors) + " |"
    lines += [header, "| -- | -- |" + " -- |" * len(detectors)]
    for t in entities:
        if not gold_counts[t]:
            continue
        cells = []
        for d in detectors.values():
            c = d["score"]["per_type"][t]
            recall = c["found"] / c["gold"]
            precision = f"{c['correct'] / c['predicted'] * 100:.0f} %" if c["predicted"] else "–"
            cells.append(f"{recall * 100:.0f} % / {precision}")
        lines.append(f"| `{t}` | {gold_counts[t]} | " + " | ".join(cells) + " |")

    if latency:
        (off_p50, off_p95), (on_p50, on_p95) = (percentiles(v) for v in latency.values())
        analyzer_p50, analyzer_p95 = percentiles([x * 1000 for x in detectors["Presidio"]["seconds"]])
        lines += [
            "",
            "## Latency added by the guardrail",
            "",
            f"Gateway round trip for each text of the dataset, {LATENCY_ROUNDS} rounds, with a mock answer "
            "(`mock_response`) so that no model time hides the difference.",
            "",
            "| Team | p50 | p95 |",
            "| -- | -- | -- |",
            f"| Without guardrail (opted out) | {off_p50:.1f} ms | {off_p95:.1f} ms |",
            f"| With `pii-fr` | {on_p50:.1f} ms | {on_p95:.1f} ms |",
            f"| Difference | {on_p50 - off_p50:+.1f} ms | {on_p95 - off_p95:+.1f} ms |",
            "",
            f"The Analyzer alone takes {analyzer_p50:.1f} ms (p50) and {analyzer_p95:.1f} ms (p95) per text; "
            "the guardrail also calls the Anonymizer and analyzes each message separately.",
        ]

    leaks = detectors["Presidio"]["score"]["leaks"]
    lines += ["", f"## What Presidio left in clear ({len(leaks)} items)", "",
              "| Text | Type | Value |", "| -- | -- | -- |"]
    lines += [f"| {row_id} | `{t}` | {value.replace(chr(10), ' ')} |" for row_id, t, value in leaks]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-llm", action="store_true", help="only Presidio and the latency part")
    parser.add_argument("--models", nargs="*", default=list(LLMS), help="Ollama models to compare")
    args = parser.parse_args()

    rows = load_dataset()
    entities, threshold, prices = gateway_settings()
    client = httpx.Client(timeout=600)

    detectors = {"Presidio": run_detector("Presidio", rows, lambda text: (presidio(client, text, entities, threshold), {}))}
    if not args.skip_llm:
        for model in args.models:
            warm_up(client, model)
            run = run_detector(model, rows, lambda text, model=model: llm(client, model, text, entities))
            detectors[model] = run | {"llm": True, "alias": LLMS.get(model)}
    for d in detectors.values():
        d["score"] = score(rows, d["predictions"], entities)

    print("Gateway latency with and without the guardrail...")
    latency = gateway_latency(rows)
    RESULTS.write_text(report(rows, entities, threshold, prices, detectors, latency))
    print(f"Results written to {RESULTS}")


if __name__ == "__main__":
    main()
