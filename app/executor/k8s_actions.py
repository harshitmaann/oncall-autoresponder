from datetime import datetime, timezone
from kubernetes import client, config

from app.executor.policy import assert_allowed

class K8sActions:
    def __init__(self):
        # In-cluster first; fallback to local kubeconfig
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self.apps = client.AppsV1Api()

    def rollout_restart_deployment(self, namespace: str, deployment: str) -> str:
        assert_allowed("rollout_restart", namespace)

        now = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}
                }
            }
        }

        self.apps.patch_namespaced_deployment(
            name=deployment,
            namespace=namespace,
            body=body,
        )

        return f"✅ Restart triggered for deployment `{deployment}` in namespace `{namespace}` at `{now}`"