# LiteLLM as it runs on Kubernetes: the official image, plus the pii-fr guardrail class and the tenant bootstrap
# scripts. Built with the build contexts `guardrails` and `scripts` (see .github/workflows/images.yml).
# compose.yaml keeps the official image and mounts the same files.
FROM ghcr.io/berriai/litellm-database:main-v1.83.14-stable

# LiteLLM loads custom guardrail classes from the directory of its config file, which the Helm chart mounts
# at /etc/litellm/config.yaml.
COPY --from=guardrails presidio_markers.py /etc/litellm/presidio_markers.py
# Run by the tenant bootstrap Job: python3 /opt/llmops-gateway/bootstrap_tenants.py
COPY --from=scripts bootstrap_tenants.py bootstrap_langfuse.py /opt/llmops-gateway/
