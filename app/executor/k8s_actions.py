from datetime import datetime, timezone
import time
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

    def verify_deployment(self, namespace: str, deployment: str, wait_seconds: int = 30) -> dict:
        """Verify rollout + readiness after an action."""
        deadline = time.time() + wait_seconds

        # Best-effort wait for rollout to settle
        while time.time() < deadline:
            dep = self.apps.read_namespaced_deployment(name=deployment, namespace=namespace)
            status = dep.status

            desired = dep.spec.replicas or 0
            updated = status.updated_replicas or 0
            available = status.available_replicas or 0
            ready = status.ready_replicas or 0

            if updated >= desired and available >= desired and ready >= desired:
                break

            time.sleep(2)

        # Final read
        dep = self.apps.read_namespaced_deployment(name=deployment, namespace=namespace)
        status = dep.status
        desired = dep.spec.replicas or 0
        updated = status.updated_replicas or 0
        available = status.available_replicas or 0
        ready = status.ready_replicas or 0

        restarted_at = (
            (dep.spec.template.metadata.annotations or {}).get("kubectl.kubernetes.io/restartedAt")
        )

        # Pod restart info using the common label selector used in your demo
        v1 = client.CoreV1Api()
        pods = v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={deployment}")
        max_restarts = 0
        pod_count = 0
        for p in pods.items:
            pod_count += 1
            if p.status.container_statuses:
                for cs in p.status.container_statuses:
                    max_restarts = max(max_restarts, cs.restart_count)

        ok = (updated >= desired and available >= desired and ready >= desired)

        return {
            "ok": ok,
            "deployment": deployment,
            "namespace": namespace,
            "desired": desired,
            "updated": updated,
            "available": available,
            "ready": ready,
            "pod_count": pod_count,
            "max_restarts": max_restarts,
            "restarted_at": restarted_at,
        }
