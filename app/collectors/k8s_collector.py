from typing import Any, Dict, List
from kubernetes import client, config

class K8sCollector:
    def __init__(self):
        try:
            config.load_incluster_config()
        except Exception:
            try:
                config.load_kube_config()
            except Exception:
                self.enabled = False
                return
        self.enabled = True
        self.v1 = client.CoreV1Api()

    def collect_basic(self, namespace: str, service: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "note": "Kubernetes client not configured."}

        pods = self._list_pods(namespace, service)
        events = self._list_events(namespace, pods)

        return {"enabled": True, "pods": pods, "events": events[:25]}

    def _list_pods(self, namespace: str, service: str) -> List[Dict[str, Any]]:
        selectors = [f"app={service}", f"service={service}"]
        pod_list = None
        for sel in selectors:
            pl = self.v1.list_namespaced_pod(namespace=namespace, label_selector=sel)
            if pl.items:
                pod_list = pl
                break
        if pod_list is None:
            pod_list = self.v1.list_namespaced_pod(namespace=namespace)

        out = []
        for p in pod_list.items[:25]:
            out.append({
                "name": p.metadata.name,
                "phase": p.status.phase,
                "node": p.spec.node_name,
                "restarts": sum(cs.restart_count for cs in (p.status.container_statuses or [])),
                "ready": all(cs.ready for cs in (p.status.container_statuses or [])) if p.status.container_statuses else False,
            })
        return out

    def _list_events(self, namespace: str, pods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pod_names = {p["name"] for p in pods}
        ev_list = self.v1.list_namespaced_event(namespace=namespace)

        out = []
        for e in reversed(ev_list.items):
            involved = getattr(e.involved_object, "name", "")
            if involved in pod_names:
                out.append({
                    "reason": e.reason,
                    "message": e.message,
                    "type": e.type,
                    "involved": involved,
                })
        return out
