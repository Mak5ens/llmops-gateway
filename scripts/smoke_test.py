"""Smoke test: call every alias of the gateway with the OpenAI SDK and check each one answers.

Run with `just smoke` once `just gateway-up` has finished.
"""

import os
import sys
import time

from openai import OpenAI

base_url = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
client = OpenAI(base_url=base_url, api_key=os.environ["LITELLM_MASTER_KEY"])
failures = []

for alias in ("chat-small", "chat-large"):
    start = time.perf_counter()
    response = client.chat.completions.create(
        model=alias,
        messages=[{"role": "user", "content": "Reply with one short sentence: what is an LLM gateway?"}],
        max_tokens=60,
    )
    elapsed = time.perf_counter() - start
    answer = (response.choices[0].message.content or "").strip()
    if not answer:
        failures.append(f"{alias}: empty answer")
    print(f"{alias}: {elapsed:.1f}s, {response.usage.prompt_tokens} tokens in, {response.usage.completion_tokens} out")
    print(f"  {answer}")

start = time.perf_counter()
embedding = client.embeddings.create(model="embed", input="Le locataire a payé son loyer en retard.")
elapsed = time.perf_counter() - start
dimensions = len(embedding.data[0].embedding)
if dimensions == 0:
    failures.append("embed: empty vector")
print(f"embed: {elapsed:.1f}s, {dimensions} dimensions")

if failures:
    sys.exit("FAIL: " + "; ".join(failures))
print("OK")
