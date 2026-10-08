"""Where the integration tests run: the Docker Compose stack of this repo, or the gateway deployed on Kubernetes by
llmops-platform. Both give the tests the same operations, so the test code is the same for both.

GATEWAY_STACK=compose (default) or kubernetes; KUBE_CONTEXT selects the cluster (default k3d-llmops).
"""

import base64
import json
import os
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


class ComposeStack:
    """The stack of compose.yaml, published on localhost. Settings come from .env."""

    def __init__(self) -> None:
        self.gateway_url = f"http://localhost:{os.environ.get('LITELLM_PORT', '4000')}"
        self.langfuse_url = f"http://localhost:{os.environ.get('LANGFUSE_PORT', '3100')}"
        self.presidio_analyzer_url = f"http://localhost:{os.environ.get('PRESIDIO_ANALYZER_PORT', '5002')}"
        self.presidio_anonymizer_url = f"http://localhost:{os.environ.get('PRESIDIO_ANONYMIZER_PORT', '5001')}"

    def compose(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True, text=True)

    def start(self) -> None:
        """Start the stack if needed: a no-op when it already runs."""
        self.compose("up", "--detach", "--wait", "--build")

    def bootstrap(self) -> str:
        """Apply config/tenants.yaml, as `just tenants` does, and return what the script printed."""
        return self.compose("run", "--rm", "--no-deps", "tenants-bootstrap").stdout

    def stop(self, service: str) -> None:
        self.compose("stop", service)

    def restart(self, service: str) -> None:
        self.compose("up", "--detach", "--wait", service)

    def logs(self, *services: str, since: str) -> str:
        """Logs of the services since an ISO timestamp or a duration like "60s"."""
        return self.compose("logs", "--no-log-prefix", "--since", since, *services).stdout

    @contextmanager
    def litellm_at_debug(self) -> Iterator[None]:
        debug = Path(__file__).with_name("compose.litellm-debug.yaml")
        self.compose("-f", "compose.yaml", "-f", str(debug), "up", "--detach", "--wait", "litellm")
        try:
            yield
        finally:
            self.compose("up", "--detach", "--wait", "litellm")


class KubernetesStack:
    """The gateway deployed by llmops-platform: LiteLLM, Presidio and Ollama in the llm-gateway namespace, Langfuse in
    the langfuse namespace. LiteLLM and Langfuse are reached through the cluster's Gateway over HTTPS, Presidio, which
    has no route, through a port-forward. Settings come from the gateway-env Secret, with the variable names of .env.

    ArgoCD repairs any manual change. Tests that stop a service or change LiteLLM's log level suspend the reconciliation
    of the llm-gateway Application meanwhile, and ArgoCD puts everything back as in Git when it resumes.
    """

    namespace = "llm-gateway"
    application = "llm-gateway"

    def __init__(self, context: str) -> None:
        self.context = context
        self.gateway_url = "https://llm.localtest.me"
        self.langfuse_url = "https://langfuse.localtest.me"
        # The cluster's local certificate authority, trusted by httpx and the OpenAI SDK through SSL_CERT_FILE.
        ca = self.kubectl("-n", "cert-manager", "get", "secret", "local-ca", "-o", "jsonpath={.data.ca\\.crt}")
        fd, self._ca = tempfile.mkstemp(prefix="llmops-ca-", suffix=".pem")
        with os.fdopen(fd, "wb") as file:
            file.write(base64.b64decode(ca))
        os.environ["SSL_CERT_FILE"] = self._ca
        self._forwards: list[subprocess.Popen] = []
        self.presidio_analyzer_url = self.port_forward("svc/presidio-analyzer", 3000)
        self.presidio_anonymizer_url = self.port_forward("svc/presidio-anonymizer", 3000)

    def kubectl(self, *args: str, namespace: bool = False) -> str:
        command = ["kubectl", "--context", self.context, *(["-n", self.namespace] if namespace else []), *args]
        return subprocess.run(command, check=True, capture_output=True, text=True).stdout

    def settings(self) -> dict[str, str]:
        secret = json.loads(self.kubectl("get", "secret", "gateway-env", "-o", "json", namespace=True))
        return {name: base64.b64decode(value).decode() for name, value in secret["data"].items()}

    def port_forward(self, target: str, port: int) -> str:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            local = probe.getsockname()[1]
        command = ["kubectl", "--context", self.context, "-n", self.namespace, "port-forward", target, f"{local}:{port}"]
        self._forwards.append(subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        deadline = time.monotonic() + 30
        while socket.socket().connect_ex(("127.0.0.1", local)) != 0:
            if time.monotonic() > deadline:
                raise RuntimeError(f"port-forward to {target} did not open")
            time.sleep(0.2)
        return f"http://localhost:{local}"

    def start(self) -> None:
        """ArgoCD deploys the stack: wait until every workload is ready."""
        for namespace in (self.namespace, "langfuse"):
            for workload in self.kubectl("-n", namespace, "get", "deployments,statefulsets", "-o", "name").split():
                self.kubectl("-n", namespace, "rollout", "status", workload, "--timeout=300s")

    def bootstrap(self) -> str:
        """Run the tenant bootstrap Job once more, from the Job ArgoCD runs after each sync, and return its output."""
        job = json.loads(self.kubectl("get", "job", "tenants-bootstrap", "-o", "json", namespace=True))
        name = f"tenants-bootstrap-{int(time.time())}"
        labels = {k: v for k, v in job["spec"]["template"]["metadata"].get("labels", {}).items() if "job-name" not in k
                  and "controller-uid" not in k}
        job["metadata"] = {"name": name, "namespace": self.namespace}
        job["spec"].pop("selector", None)
        job["spec"]["template"]["metadata"]["labels"] = labels
        job.pop("status", None)
        subprocess.run(["kubectl", "--context", self.context, "create", "-f", "-"], input=json.dumps(job), check=True,
                       capture_output=True, text=True)
        try:
            self.kubectl("wait", f"job/{name}", "--for=condition=Complete", "--timeout=180s", namespace=True)
            return self.kubectl("logs", f"job/{name}", namespace=True)
        finally:
            self.kubectl("delete", "job", name, "--wait=false", namespace=True)

    def _reconcile(self, enabled: bool) -> None:
        annotation = "argocd.argoproj.io/skip-reconcile"
        value = f"{annotation}-" if enabled else f"{annotation}=true"
        self.kubectl("-n", "argocd", "annotate", "application", self.application, value, "--overwrite")
        if not enabled:
            # The annotation stops new reconciliations, not one already running: one started a moment before (after
            # the previous test resumed, for instance) would still revert the change that follows.
            time.sleep(10)

    def _resume(self) -> None:
        self._reconcile(True)
        # The status ArgoCD shows still dates from before the pause: ask for a new comparison, wait until it is done
        # (ArgoCD then removes the annotation), then until the workloads are back as in Git.
        refresh = "argocd.argoproj.io/refresh"
        self.kubectl("-n", "argocd", "annotate", "application", self.application, f"{refresh}=hard", "--overwrite")
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            app = json.loads(self.kubectl("-n", "argocd", "get", "application", self.application, "-o", "json"))
            status = app.get("status", {})
            if (refresh not in app["metadata"].get("annotations", {})
                    and status.get("sync", {}).get("status") == "Synced"
                    and status.get("health", {}).get("status") == "Healthy"):
                return
            time.sleep(2)
        raise RuntimeError(f"Application {self.application} not synced and healthy after resuming")

    def stop(self, service: str) -> None:
        self._reconcile(False)
        self.kubectl("scale", f"deployment/{service}", "--replicas=0", namespace=True)
        self.kubectl("wait", "pod", "-l", f"app.kubernetes.io/name={service}", "--for=delete", "--timeout=120s",
                     namespace=True)

    def restart(self, service: str) -> None:
        self._resume()
        self.kubectl("wait", f"deployment/{service}", "--for=jsonpath={.status.readyReplicas}=1", "--timeout=300s",
                     namespace=True)

    def logs(self, *services: str, since: str) -> str:
        """Logs of the services since an ISO timestamp or a duration like "60s"."""
        option = f"--since={since}" if since.endswith("s") and since[:-1].isdigit() else f"--since-time={since}"
        return "".join(self.kubectl("logs", pod, option, namespace=True) for service in services
                       for pod in self.pods(service))

    def pods(self, service: str) -> list[str]:
        """Pods of a service, without the ones being deleted: after a restart, the old LiteLLM pod lingers for up to
        90 s (its termination grace period), and `kubectl logs deployment/...` may pick it."""
        found = json.loads(self.kubectl("get", "pods", "-l", f"app.kubernetes.io/name={service}", "-o", "json",
                                        namespace=True))
        return [f"pod/{pod['metadata']['name']}" for pod in found["items"] if "deletionTimestamp" not in pod["metadata"]]

    def _wait_for_gateway(self) -> None:
        """After LiteLLM restarts, Envoy keeps sending requests to the old pod for a few seconds: wait until ten
        health checks in a row go through the Gateway to a live pod."""
        deadline, in_a_row = time.monotonic() + 120, 0
        while in_a_row < 10:
            if time.monotonic() > deadline:
                raise RuntimeError("LiteLLM does not answer steadily through the Gateway")
            try:
                ok = httpx.get(f"{self.gateway_url}/health/liveliness", timeout=5).status_code == 200
            except httpx.HTTPError:
                ok = False
            in_a_row = in_a_row + 1 if ok else 0
            time.sleep(0.5)

    @contextmanager
    def litellm_at_debug(self) -> Iterator[None]:
        self._reconcile(False)
        try:
            self.kubectl("set", "env", "deployment/litellm", "LITELLM_LOG=DEBUG", namespace=True)
            self.kubectl("rollout", "status", "deployment/litellm", "--timeout=300s", namespace=True)
            self._wait_for_gateway()
            if "LITELLM_LOG=DEBUG" not in self.kubectl("set", "env", "deployment/litellm", "--list", namespace=True):
                raise RuntimeError("ArgoCD reverted LITELLM_LOG=DEBUG on the LiteLLM deployment")
            yield
        finally:
            self._resume()
            self.kubectl("rollout", "status", "deployment/litellm", "--timeout=300s", namespace=True)
            self._wait_for_gateway()

    def close(self) -> None:
        for forward in self._forwards:
            forward.terminate()
        Path(self._ca).unlink(missing_ok=True)


def from_environment() -> ComposeStack | KubernetesStack:
    target = os.environ.get("GATEWAY_STACK", "compose")
    if target == "compose":
        return ComposeStack()
    if target == "kubernetes":
        return KubernetesStack(os.environ.get("KUBE_CONTEXT", "k3d-llmops"))
    raise ValueError(f"GATEWAY_STACK must be compose or kubernetes, not {target!r}")
