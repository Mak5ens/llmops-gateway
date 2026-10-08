# ADR-015: Fix the numbered markers of LiteLLM's Presidio guardrail in a subclass

- **Status:** Accepted
- **Date:** 2026-09-30

## Context

The gateway masks French personal data before inference and puts it back into the answer (LAB-115). LiteLLM ships a Presidio guardrail for this: with `output_parse_pii`, it replaces each detection with a numbered marker such as `<PERSON_1>`, keeps the original values for the request, and replaces the markers in the answer. We use it rather than a gateway hook of our own.

Tested on the running stack (LiteLLM 1.83.14, Presidio 2.2.362), the markers break in two ways:

1. **Overlapping detections garble the prompt.** Presidio drops a detection contained in another only when both have the same type, so it returns an address with the city inside it as a `LOCATION`, and an IBAN with `FR76` as a `LOCATION`. LiteLLM replaces each detection at its original position; the model received `j habite au FR_ADDRESS_2ON_4. Mon IBAN est IBAN_CODE_57890 189` and nothing could be put back. Upstream issue BerriAI/litellm#42130, open.
2. **Each message is numbered from 1.** With "Le bailleur est Jean Martin" then "La locataire est Marie Dupont", both names became `<PERSON_1>`, the second value overwrote the first, and the answer named Marie Dupont as the landlord. Upstream issue BerriAI/litellm#31959, open since 2026-07-02; the fix proposed in #31978 is not merged.

The first bug hits most French addresses and every IBAN, because the spaCy model tags city names and country codes. The second hits every conversation longer than one message, which is the normal case for the lease assistant. Both lead to a wrong answer, not only a less private one.

## Options considered

| Option | Pros | Cons |
| -- | -- | -- |
| A. Subclass LiteLLM's Presidio guardrail and override the one method that builds the markers | About 40 lines; every other behaviour (analysis, thresholds, streaming, unmasking, per-team opt-out) stays LiteLLM's; loaded by LiteLLM's documented custom guardrail mechanism | Relies on a private method (`_finalize_presidio_anonymize_numbered_tokens`), which can change on any LiteLLM upgrade |
| B. Merge overlaps in the Presidio Analyzer (a wrapper in `docker/presidio-analyzer/server.py`) | LiteLLM stays untouched | Fixes only the first bug; LiteLLM applies its score threshold after the Analyzer, so a low-score address could absorb a confident city and then be dropped, leaving the city in clear, unless the threshold also moves to the Analyzer |
| C. Our own guardrail from scratch, calling Presidio directly | Full control | Re-implements streaming, unmasking and logging that LiteLLM already has; more code to test and maintain |
| D. Keep the stock guardrail and document the bugs | No code | Wrong names and garbled prompts on the main use case |
| E. Wait for an upstream release | No code | No date: #31959 and its fix #31978 have been open since July 2026 |

## Decision

We choose **A**: `guardrails/presidio_markers.py` defines `PresidioStableMarkers`, a subclass of LiteLLM's Presidio guardrail, and `config/litellm.yaml` loads it with `guardrail: presidio_markers.PresidioStableMarkers`. The override:

- merges each group of overlapping detections into one span covering the whole group, with the type of the longest detection, so no character of any detection stays in clear;
- numbers markers across all the messages of a request, and gives a value seen before its marker back.

The score threshold still applies first, in LiteLLM, so a detection below it cannot absorb one above it.
Option B was implemented first and dropped: it fixed only half of the problem.

## Consequences

- The model receives `Le bailleur est <PERSON_1>, domicilié au <FR_ADDRESS_2>.` and `La locataire est <PERSON_3>, <IBAN_CODE_4>. <PERSON_1> est-il joignable ?`, checked in LiteLLM's debug log, and the answer comes back with the right names.
- A LiteLLM upgrade must be checked against this class: `litellm` is pinned in `pyproject.toml` to the image version, and `tests/unit/test_presidio_markers.py` runs the override against it. If the private method changes, the unit tests fail before the stack does.
- Merged spans can hide a little more than needed (the word before an IBAN when spaCy tags both), never less.
- We remove the class once LiteLLM fixes both issues, and upstream the fix if #31978 stalls.
- Update, 2026-10-08 (LiteLLM 1.104.1, LAB-130): both bugs are still upstream, and the overridden method kept its signature, so the class stays. LiteLLM 1.84 added a trap: the proxy only gives a streamed answer to a guardrail whose own class defines `async_post_call_streaming_iterator_hook`, not to a subclass that inherits it, and only if the guardrail runs at `post_call`. The class now redefines the hook as a pass-through, `pii-fr` runs at `[pre_call, post_call]`, and a unit test checks the hook stays defined.
