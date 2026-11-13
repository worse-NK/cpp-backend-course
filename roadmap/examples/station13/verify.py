#!/usr/bin/env python3
"""Offline checks of this lab's file contract, not Kubernetes API validation.

Only reads local files. Does not run Docker, kubectl, kind, install packages,
create sockets, change contexts or apply resources.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
NAMESPACE = "course13"
CLUSTER = "course-station13-v1"


def load(name: str) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"{name}: duplicate field {key!r}")
            obj[key] = value
        return obj
    return json.loads((HERE / name).read_text(encoding="utf-8"), object_pairs_hook=unique)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_files() -> list[str]:
    ns = load("namespace.json")
    require(ns["kind"] == "Namespace" and ns["metadata"]["name"] == NAMESPACE,
            "namespace must be the dedicated course13")
    namespaced = ["configmap.json", "deployment.json", "service.json",
                  "pdb-example.json", "hpa-example.json", "role-example.json",
                  "networkpolicy-example.json"]
    for filename in namespaced:
        item = load(filename)
        require(item["metadata"]["namespace"] == NAMESPACE,
                f"{filename}: namespace must be explicit")
    d = load("deployment.json")["spec"]
    template = d["template"]
    p = template["spec"]
    c = p["containers"][0]
    s = load("service.json")["spec"]
    labels = template["metadata"]["labels"]
    require(d["selector"]["matchLabels"] == labels == s["selector"],
            "controller/template/service labels differ")
    require(d["replicas"] == 2, "baseline must have two replicas")
    require(d["strategy"]["rollingUpdate"] == {"maxSurge": 1, "maxUnavailable": 0},
            "unexpected baseline release budget")
    require(c["image"] == "course-api:station13-v1" and c["imagePullPolicy"] == "Never",
            "baseline must use the explicitly loaded local image")
    require(c["name"] == "api" and len(p["containers"]) == 1, "one explicit API container expected")
    require(c["ports"] == [{"name": "http", "containerPort": 8080}], "listener port mismatch")
    require(s["type"] == "ClusterIP" and s["ports"] == [
        {"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}],
        "Service must be internal and target the named listener")
    for kind, path in (("startupProbe", "/livez"), ("livenessProbe", "/livez"),
                       ("readinessProbe", "/readyz")):
        require(c[kind]["httpGet"] == {"path": path, "port": "http"},
                f"{kind}: probe path/port mismatch")
        require(c[kind]["timeoutSeconds"] > 0 and c[kind]["failureThreshold"] > 0,
                "probe budgets must be finite positive values")
    require(p["terminationGracePeriodSeconds"] == 15, "expected documented grace budget")
    require("lifecycle" not in c, "baseline does not teach an unbudgeted preStop sleep")
    require(c["resources"] == {"requests": {"cpu": "100m", "memory": "64Mi"},
                                "limits": {"cpu": "500m", "memory": "128Mi"}},
            "resource arithmetic and manifest differ")
    env = {x["name"]: x for x in c["env"]}
    require(env["APP_VERSION"]["valueFrom"]["configMapKeyRef"] ==
            {"name": "course-api-config", "key": "APP_VERSION"}, "config reference mismatch")
    require(env["APP_INSTANCE"]["valueFrom"]["fieldRef"]["fieldPath"] == "metadata.name",
            "instance identity must come from this Pod's metadata")
    require(load("configmap.json")["data"] == {"APP_VERSION": "v1"},
            "baseline configuration mismatch")
    require(p["automountServiceAccountToken"] is False, "no unnecessary API token mount")
    sc = p["securityContext"]
    require(sc["runAsNonRoot"] is True and sc["runAsUser"] == 65532
            and sc["runAsGroup"] == 65532 and sc["fsGroup"] == 65532,
            "non-root / temporary-volume ownership contract mismatch")
    require(sc["seccompProfile"] == {"type": "RuntimeDefault"}, "seccomp contract mismatch")
    require(c["securityContext"] == {"allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
            "process restrictions changed")
    require(p["volumes"] == [{"name": "tmp", "emptyDir": {"sizeLimit": "16Mi"}}]
            and c["volumeMounts"] == [{"name": "tmp", "mountPath": "/tmp"}],
            "only the explicit temporary writable volume is allowed")
    for field in ("hostNetwork", "hostPID", "hostIPC"):
        require(not p.get(field, False), f"{field}: host sharing is not part of the lab")
    require(not c["securityContext"].get("privileged", False), "no privileged application")
    require(load("pdb-example.json")["spec"]["minAvailable"] == 1, "PDB example mismatch")
    hpa = load("hpa-example.json")
    require(hpa["apiVersion"] == "autoscaling/v2", "HPA API version mismatch")
    require(hpa["spec"]["metrics"][0]["resource"]["target"] ==
            {"type": "Utilization", "averageUtilization": 60}, "HPA denominator scenario changed")
    role = load("role-example.json")
    require(role["kind"] == "Role" and role["rules"] == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list", "watch"]}],
        "example Role must not grant create, Secret access or cluster administration")
    policy = load("networkpolicy-example.json")["spec"]
    require(policy["ingress"] == [] and policy["policyTypes"] == ["Ingress"],
            "explanatory deny-ingress policy changed")
    kind = (HERE / "kind.yaml").read_text(encoding="utf-8")
    require(f"name: {CLUSTER}" in kind and 'apiServerAddress: "127.0.0.1"' in kind,
            "kind must use its dedicated name and loopback API endpoint")
    require(re.search(r"kindest/node:v1\.36\.4@sha256:[0-9a-f]{64}\b", kind) is not None,
            "node image must pin version and digest")
    require("extraPortMappings" not in kind and "extraMounts" not in kind,
            "no host publication/mounts in the basic lab")
    return ["JSON parsed with duplicate-field rejection; names/namespace/selectors match",
            "Service/probes/listener/config and resource arithmetic agree",
            "application restrictions and explicit temporary volume match the text",
            "versioned examples and local kind endpoint match the lab contract",
            "NOT CHECKED: Kubernetes API validation, image build, cluster runtime or traffic"]


if __name__ == "__main__":
    for result in check_files():
        print(result)
