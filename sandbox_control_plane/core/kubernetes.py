from functools import lru_cache

from kubernetes import client, config


class KubernetesClient:
    """Generic Kubernetes access: config loading + typed API accessors.

    Domain-agnostic — each domain builds its own gateway on top of this.
    """

    def __init__(self) -> None:
        try:
            config.load_incluster_config()  # when deployed
        except config.ConfigException:
            config.load_kube_config()  # local dev
        self._api = client.ApiClient()

    def custom_objects(self) -> client.CustomObjectsApi:
        return client.CustomObjectsApi(self._api)

    def core_v1(self) -> client.CoreV1Api:
        return client.CoreV1Api(self._api)

    def core_v1_exec(self) -> client.CoreV1Api:
        """CoreV1Api on its own ApiClient, for `stream()` only — it swaps api_client.request, so
        sharing would misroute concurrent REST calls. Shares the Configuration; caller closes it."""
        return client.CoreV1Api(client.ApiClient(self._api.configuration))


@lru_cache
def get_kubernetes_client() -> KubernetesClient:
    return KubernetesClient()
