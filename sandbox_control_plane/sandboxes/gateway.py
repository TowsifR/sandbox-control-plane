"""Kubernetes access for `Sandbox` claims — the only Sandbox-CRD-aware code."""

from kubernetes.client.rest import ApiException

from ..core.kubernetes import KubernetesClient

GROUP = "platform.example.io"
VERSION = "v1alpha1"
PLURAL = "sandboxes"
LABEL = f"{GROUP}/sandbox"  # stamped on the pod by the Composition


class SandboxGateway:
    def __init__(self, k8s: KubernetesClient, namespace: str) -> None:
        self._api = k8s.custom_objects()
        self._core = k8s.core_v1()
        self._ns = namespace

    def create(self, name: str, owner: str, size: str, image: str) -> None:
        body = {
            "apiVersion": f"{GROUP}/{VERSION}",
            "kind": "Sandbox",
            "metadata": {"name": name, "namespace": self._ns},
            "spec": {"owner": owner, "size": size, "image": image},
        }
        try:
            self._api.create_namespaced_custom_object(GROUP, VERSION, self._ns, PLURAL, body)
        except ApiException as e:
            if e.status != 409:  # already exists — create is idempotent
                raise

    def get(self, name: str) -> dict | None:
        try:
            return self._api.get_namespaced_custom_object(GROUP, VERSION, self._ns, PLURAL, name)
        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list(self) -> list[dict]:
        return self._api.list_namespaced_custom_object(GROUP, VERSION, self._ns, PLURAL)["items"]

    def is_ready(self, name: str) -> bool:
        obj = self.get(name) or {}
        conditions = (obj.get("status") or {}).get("conditions") or []
        return any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)

    def pod_name(self, namespace: str, name: str) -> str | None:
        """The sandbox's pod — `namespace` is the workload ns from the claim's status, not self._ns."""
        pods = self._core.list_namespaced_pod(
            namespace, label_selector=f"{LABEL}={name}", field_selector="status.phase=Running"
        )
        # phase comes from the workflow, so it can still say running mid-teardown.
        live = [p for p in pods.items if not p.metadata.deletion_timestamp]
        return live[0].metadata.name if live else None

    def delete(self, name: str) -> None:
        try:
            self._api.delete_namespaced_custom_object(GROUP, VERSION, self._ns, PLURAL, name)
        except ApiException as e:
            if e.status != 404:  # already gone — delete is idempotent
                raise
