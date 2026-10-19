# LiteLLM of the gateway: the official image, plus the pii-fr guardrail class, the tenant bootstrap scripts and fixes
# to LiteLLM not released yet (patch_litellm.py). Built with the build contexts `guardrails` and `scripts`
# (see .github/workflows/images.yml and compose.yaml); compose.yaml mounts the config and the guardrail over it.
FROM ghcr.io/berriai/litellm-database:v1.106.0

# Fails the build if a fix no longer applies to this LiteLLM version.
COPY patch_litellm.py /tmp/patch_litellm.py
RUN python3 /tmp/patch_litellm.py && rm /tmp/patch_litellm.py

# LiteLLM loads custom guardrail classes from the directory of its config file, which the Helm chart mounts
# at /etc/litellm/config.yaml.
COPY --from=guardrails presidio_markers.py /etc/litellm/presidio_markers.py
# Run by the tenant bootstrap Job: python3 /opt/llmops-gateway/bootstrap_tenants.py
COPY --from=scripts bootstrap_tenants.py bootstrap_langfuse.py /opt/llmops-gateway/
