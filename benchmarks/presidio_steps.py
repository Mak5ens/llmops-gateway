"""Measure what each layer of the Analyzer adds, and write benchmarks/steps.md and benchmarks/steps_examples.json.

The same texts go through three Analyzers, from Presidio out of the box to the one the gateway runs:

1. the official image, as `docker run` starts it: English spaCy model and stock recognizers;
2. our image with the French spaCy model, but still the stock recognizers (benchmarks/presidio-stock/);
3. the gateway's Analyzer: French model and the French recognizers of docker/presidio-analyzer/pii_recognizers/.

The first two run in temporary containers, stopped at the end. Each Analyzer is scored like the benchmark scores
Presidio (run_bench.py): entities and threshold of the pii-fr guardrail, overlapping detections merged.
steps_examples.json holds the detections of each Analyzer on a few short texts, with Presidio's explanation
(recognizer, score, context word, checksum), for the article on maxence-labbe.fr.

Run with `just presidio-steps` (starts the stack first).
"""

import json
import subprocess
import time
from datetime import date
from pathlib import Path

import httpx

from run_bench import ANALYZER_URL, DATASET, ROOT, gateway_settings, load_dataset, merge_overlaps, pct, score

HERE = Path(__file__).parent
STEPS = HERE / "steps.md"
EXAMPLES_OUT = HERE / "steps_examples.json"
ANALYZER_TAG = "2.2.362"
# Name, label, image, port, language, extra `docker run` arguments. None for the image: the gateway's Analyzer.
ANALYZERS = [
    ("stock", "Official image (English model, stock recognizers)", f"mcr.microsoft.com/presidio-analyzer:{ANALYZER_TAG}",
     5102, "en", []),
    ("fr-model", "+ French spaCy model", f"llmops-gateway/presidio-analyzer:{ANALYZER_TAG}-fr", 5103, "fr", [
        "-e", "ANALYZER_CONF_FILE=/config/analyzer.yaml", "-e", "NLP_CONF_FILE=/config/nlp.yaml",
        "-e", "RECOGNIZER_REGISTRY_CONF_FILE=/stock/recognizers.yaml",
        "-v", f"{ROOT / 'config' / 'presidio'}:/config:ro", "-v", f"{HERE / 'presidio-stock'}:/stock:ro",
    ]),
    ("gateway", "+ French recognizers (the gateway)", None, None, "fr", []),
]

# Short texts for the article: every value is fictitious, and every identifier has valid check digits.
EXAMPLES = {
    "letter": (
        "Camille Roussel\n8 allée des Tilleuls\n33000 Bordeaux\n\nBonjour,\n\n"
        "Je vous écris au sujet du remboursement de soins de ma mère, Mme Josiane Roussel. Son numéro de sécurité "
        "sociale est le 2 52 07 33 063 112 03 et son numéro fiscal le 30 23 217 600 053.\n\n"
        "Le remboursement peut partir sur le compte FR76 3000 6000 0112 3456 7890 189, ou sur la carte "
        "2221 0000 1234 5673.\n\nVous pouvez me joindre au 06 12 34 56 78 ou à camille.roussel@example.fr.\n\n"
        "Cordialement,\nCamille"
    ),
    "message": (
        "Salut Anaïs, le Docteur Camus a validé l'arrêt. Tu peux le déposer chez Étienne avant vendredi ? "
        "Sinon appelle-moi au 01 46 39 90 88. Bises, Olivier"
    ),
    "form": (
        "Nom : Buisson\nPrénom : Hortense\nAdresse : 21 rue Jean Moulin\n74000 Annecy\n"
        "N° de sécurité sociale : 1 85 05 78 006 084 91\nTéléphone : 04 50 12 34 56"
    ),
}


def start(name: str, image: str, port: int, args: list[str]) -> str:
    container = f"presidio-steps-{name}"
    subprocess.run(["docker", "rm", "-f", container], capture_output=True)
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", container, "-p", f"127.0.0.1:{port}:3000",
         "-e", "GUNICORN_CMD_ARGS=--no-control-socket", *args, image],
        check=True, capture_output=True,
    )
    return container


def wait_healthy(client: httpx.Client, url: str, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if client.get(f"{url}/health").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    raise TimeoutError(f"{url} not healthy after {timeout} s")


def analyze(client: httpx.Client, url: str, language: str, text: str, entities: list[str], threshold: float,
            explain: bool = False) -> list[dict]:
    # No entity list in the request: the stock Analyzers do not know FR_NIR and the other French types, and would
    # reject the request. Filtering afterwards keeps the same entities as the guardrail.
    response = client.post(f"{url}/analyze", json={
        "text": text, "language": language, "score_threshold": threshold, "return_decision_process": explain,
    })
    response.raise_for_status()
    return sorted((r for r in response.json() if r["entity_type"] in entities), key=lambda r: r["start"])


def explained(text: str, results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        e = r.get("analysis_explanation") or {}
        out.append({
            "type": r["entity_type"], "start": r["start"], "end": r["end"], "text": text[r["start"] : r["end"]],
            "score": round(r["score"], 2), "recognizer": e.get("recognizer"),
            "original_score": e.get("original_score"), "context_word": e.get("supportive_context_word") or None,
            "checksum": e.get("validation_result"),
        })
    return out


def report(rows: list[dict], entities: list[str], threshold: float, scores: dict[str, dict]) -> str:
    lines = [
        "# What each layer of the Analyzer adds",
        "",
        f"Generated by `just presidio-steps` on {date.today().isoformat()}. Do not edit by hand: rerun the command.",
        "",
        f"Dataset: [`{DATASET.name}`]({DATASET.name}), {len(rows)} texts, scored as in [`results.md`](results.md): "
        f"the {len(entities)} entity types of the `pii-fr` guardrail, score threshold {threshold}, overlapping "
        "detections merged. The official image only has an English model, so it gets the texts as English.",
        "",
        "| Analyzer | Precision | Recall | Fully masked | Items left in clear |",
        "| -- | -- | -- | -- | -- |",
    ]
    for (_, label, *_), s in zip(ANALYZERS, scores.values(), strict=True):
        lines.append(f"| {label} | {pct(s['precision'])} | {pct(s['recall'])} | {pct(s['masked'])} | {len(s['leaks'])} |")
    lines += ["", "## Recall per entity type", "", "| Type | Items | " + " | ".join(n for n, *_ in ANALYZERS) + " |",
              "| -- | -- |" + " -- |" * len(ANALYZERS)]
    for t in entities:
        gold = next(iter(scores.values()))["per_type"][t]["gold"]
        if not gold:
            continue
        cells = [pct(s["per_type"][t]["found"] / gold) for s in scores.values()]
        lines.append(f"| `{t}` | {gold} | " + " | ".join(cells) + " |")
    lines += ["", "## Items left in clear, per type", "", "| Type | " + " | ".join(n for n, *_ in ANALYZERS) + " |",
              "| --" + " | --" * len(ANALYZERS) + " |"]
    for t in entities:
        counts = [sum(leak[1] == t for leak in s["leaks"]) for s in scores.values()]
        if any(counts):
            lines.append(f"| `{t}` | " + " | ".join(str(c) for c in counts) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = load_dataset()
    entities, threshold, _ = gateway_settings()
    containers, scores, examples = [], {}, {key: {"text": text} for key, text in EXAMPLES.items()}
    with httpx.Client(timeout=120) as client:
        try:
            for name, _, image, port, language, args in ANALYZERS:
                url = ANALYZER_URL
                if image:
                    containers.append(start(name, image, port, args))
                    url = f"http://localhost:{port}"
                wait_healthy(client, url)
                predictions = []
                for i, row in enumerate(rows, 1):
                    found = analyze(client, url, language, row["text"], entities, threshold)
                    predictions.append([{"type": r["entity_type"], "start": r["start"], "end": r["end"]}
                                        for r in merge_overlaps(found)])
                    print(f"\r{name}: {i}/{len(rows)}", end="", flush=True)
                print()
                scores[name] = score(rows, predictions, entities)
                for key, text in EXAMPLES.items():
                    examples[key][name] = explained(text, analyze(client, url, language, text, entities, threshold, True))
        finally:
            for container in containers:
                subprocess.run(["docker", "stop", container], capture_output=True)

    STEPS.write_text(report(rows, entities, threshold, scores))
    EXAMPLES_OUT.write_text(json.dumps(examples, ensure_ascii=False, indent=1) + "\n")
    print(f"Results written to {STEPS} and {EXAMPLES_OUT}")


if __name__ == "__main__":
    main()
