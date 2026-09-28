"""Fallback test: stop ollama-large and check chat-large still answers, served by chat-small.

Worst case on purpose: chat-large is called first, so the gateway holds an open connection to the server
that then disappears. Run with `just fallback-test`, which restarts ollama-large afterwards.
"""

import os
import subprocess
import sys
import time

from openai import OpenAI

MAX_SECONDS = 30  # chat-large timeout (20 s) + retry + answer from chat-small

base_url = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
client = OpenAI(base_url=base_url, api_key=os.environ["LITELLM_MASTER_KEY"], max_retries=0)


def ask_chat_large():
    start = time.perf_counter()
    raw = client.chat.completions.with_raw_response.create(
        model="chat-large",
        messages=[{"role": "user", "content": "Say hello in French."}],
        max_tokens=20,
    )
    return raw, time.perf_counter() - start


raw, elapsed = ask_chat_large()
print(f"Before outage: chat-large served by {raw.headers.get('x-litellm-model-group')} in {elapsed:.1f}s")

subprocess.run(["docker", "compose", "stop", "ollama-large"], check=True, capture_output=True)
print("ollama-large stopped")

raw, elapsed = ask_chat_large()
served_by = raw.headers.get("x-litellm-model-group")
answer = (raw.parse().choices[0].message.content or "").strip()
print(f"During outage: chat-large served by {served_by} in {elapsed:.1f}s")
print(f"  {answer}")

if not answer:
    sys.exit("FAIL: empty answer")
if served_by != "chat-small":
    sys.exit(f"FAIL: expected chat-small to serve the request, got {served_by}")
if elapsed > MAX_SECONDS:
    sys.exit(f"FAIL: fallback took {elapsed:.1f}s, more than {MAX_SECONDS}s")
print("OK: fallback chat-large -> chat-small works")
