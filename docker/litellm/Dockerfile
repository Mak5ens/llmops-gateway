# LiteLLM of the gateway: the official image, plus the pii-fr guardrail class, the tenant bootstrap scripts and fixes
# to LiteLLM not released yet (patch_litellm.py). Built with the build contexts `guardrails` and `scripts`
# (see .github/workflows/images.yml and compose.yaml); compose.yaml mounts the config and the guardrail over it.
FROM ghcr.io/berriai/litellm-database:v1.106.4

# certifi of the base image bundles emSign root CAs with compromised intermediate keys (GHSA-6q48-6c7w-9gw2, critical):
# the supply chain scan refuses it. The image's virtual environment has no pip, hence uv, not kept in the image.
# Remove once the base image ships certifi 2026.10.18 or later.
RUN --mount=from=ghcr.io/astral-sh/uv:0.13.1,source=/uv,target=/bin/uv \
    uv pip install --python /app/.venv/bin/python3 --no-cache "certifi==2026.10.23"

# Fails the build if a fix no longer applies to this LiteLLM version.
COPY patch_litellm.py /tmp/patch_litellm.py
RUN python3 /tmp/patch_litellm.py && rm /tmp/patch_litellm.py

# LiteLLM loads custom guardrail classes from the directory of its config file, which the Helm chart mounts
# at /etc/litellm/config.yaml.
COPY --from=guardrails presidio_markers.py /etc/litellm/presidio_markers.py
# Run by the tenant bootstrap Job: python3 /opt/llmops-gateway/bootstrap_tenants.py
COPY --from=scripts bootstrap_tenants.py bootstrap_langfuse.py /opt/llmops-gateway/
