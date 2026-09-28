"""Smoke test: call the gateway with the OpenAI SDK and check the local model answers.

Run with `make smoke` once `make gateway-up` has finished.
"""

import os
import sys
import time

from openai import OpenAI

base_url = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
client = OpenAI(base_url=base_url, api_key=os.environ["LITELLM_MASTER_KEY"])

start = time.perf_counter()
response = client.chat.completions.create(
    model="local-chat",
    messages=[{"role": "user", "content": "Reply with one short sentence: what is an LLM gateway?"}],
    max_tokens=60,
)
elapsed = time.perf_counter() - start

answer = (response.choices[0].message.content or "").strip()
if not answer:
    sys.exit(f"FAIL: empty answer from {base_url}")

print(f"OK in {elapsed:.1f}s, served by {response.model}")
print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
print(f"Answer: {answer}")
