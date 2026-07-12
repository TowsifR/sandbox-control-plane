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

    def core_v1(self) -> client.CoreV1Api:  # pods/exec — for the interactive terminal
        return client.CoreV1Api(self._api)


@lru_cache
def get_kubernetes_client() -> KubernetesClient:
    return KubernetesClient()
