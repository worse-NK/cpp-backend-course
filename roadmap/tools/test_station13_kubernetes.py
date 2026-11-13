#!/usr/bin/env python3
"""Station13 structural/source-contract tests and optional offline C++ build.

Never invokes Docker, kind or kubectl; never starts the HTTP listener.
For the app compile/self-test set COURSE_HTTPLIB_INCLUDE to an already verified
cpp-httplib0.59.0 include directory. This test does not download dependencies.
"""
from __future__ import annotations

import importlib.util
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from html.parser import HTMLParser

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]
sys.path.insert(0, str(TOOLS))
import build_stations
from checkpoint_data import with_checkpoints, normalize_prompt

SOURCE = ROOT / "roadmap/content/station13.json"
LAB = ROOT / "roadmap/examples/station13"

# Published tests must work without private authoring records. These concrete
# primary documents are part of the public chapter's editorial contract; a
# generic documentation home page cannot satisfy a section's coverage.
K8S_DOCS = "https://v1-36.docs.kubernetes.io/docs/"
PRIMARY_SOURCES = {
    "learning-route": ("concepts/overview/components/",),
    "why-cluster": ("https://kind.sigs.k8s.io/docs/user/quick-start/",),
    "objects-and-reconciliation": ("concepts/overview/working-with-objects/",),
    "pod-identity": ("concepts/workloads/pods/", "concepts/workloads/pods/pod-lifecycle/"),
    "control-plane-and-node": ("concepts/overview/components/",),
    "deployment-reading": ("concepts/workloads/controllers/deployment/",),
    "images-and-release": ("concepts/containers/images/",),
    "configuration-update": ("concepts/configuration/configmap/",),
    "resource-contract": ("concepts/configuration/manage-resources-containers/",),
    "service-and-endpoints": ("concepts/services-networking/service/",),
    "dns-and-cni": ("concepts/services-networking/dns-pod-service/",
                    "concepts/cluster-administration/networking/"),
    "ingress-and-gateway": ("concepts/services-networking/ingress/",),
    "connection-lifetime": ("concepts/workloads/pods/pod-lifecycle/",),
    "probe-questions": ("concepts/workloads/pods/probes/",),
    "startup-and-restart": ("concepts/workloads/pods/pod-lifecycle/",
                            "tasks/debug/debug-application/debug-pods/"),
    "termination-timeline": ("concepts/workloads/pods/pod-lifecycle/",),
    "cpp-drain-contract": ("https://github.com/yhirose/cpp-httplib/tree/v0.59.0",
                           "https://man7.org/linux/man-pages/man2/sigwaitinfo.2.html",
                           "https://man7.org/linux/man-pages/man3/pthread_sigmask.3.html"),
    "filesystem-lifetimes": ("concepts/storage/volumes/",),
    "pv-pvc-storageclass": ("concepts/storage/persistent-volumes/",),
    "statefulsets-not-databases": ("concepts/workloads/controllers/statefulset/",
                                  "concepts/extend-kubernetes/operator/"),
    "jobs-and-duplicate-work": ("concepts/workloads/controllers/job/",),
    "rollout-budget": ("concepts/workloads/controllers/deployment/",),
    "scheduling-and-failure-domains": ("concepts/scheduling-eviction/assign-pod-node/",),
    "hpa-loop": ("concepts/workloads/autoscaling/horizontal-pod-autoscale/",),
    "pdb-boundaries": ("concepts/workloads/pods/disruptions/",),
    "namespace-and-rbac": ("concepts/security/rbac-good-practices/",
                           "concepts/security/multi-tenancy/"),
    "secret-lifecycle": ("concepts/configuration/secret/",),
    "process-security": ("tasks/configure-pod-container/security-context/",),
    "networkpolicy-and-boundaries": ("concepts/services-networking/network-policies/",),
    "lab-route": ("https://kind.sigs.k8s.io/docs/user/configuration/",
                  "https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0"),
    "lab-deploy-and-observe": ("https://github.com/yhirose/cpp-httplib/tree/v0.59.0",
                              "tasks/inject-data-application/environment-variable-expose-pod-information/"),
    "lab-readiness-rollout": ("concepts/workloads/pods/probes/",
                              "concepts/configuration/configmap/",
                              "concepts/workloads/controllers/deployment/"),
    "diagnostic-path-and-interview": ("tasks/debug/debug-application/debug-pods/",),
    "kubernetes-final-workbook": ("concepts/workloads/pods/pod-lifecycle/",),
}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Fragment(HTMLParser):
    VOID = {"br", "hr", "img", "input", "meta", "link", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError(f"unbalanced HTML at </{tag}>")


class Station13(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(SOURCE)
        cls.resolved = with_checkpoints(cls.data)

    def test_canonical_schema_and_meta(self):
        build_stations.validate(self.data, SOURCE)
        self.assertEqual(self.data["meta"]["number"], 13)
        self.assertEqual(self.data["meta"]["sourceFile"], "cpp_station13_kubernetes.html")
        self.assertEqual(self.data["meta"]["storeKey"], "cpp_station13_progress_v1")

    def test_complete_route(self):
        self.assertEqual(len(self.data["substations"]), 8)
        self.assertEqual(len(self.data["theory"]), 34)
        for module in self.data["substations"]:
            sections = [s for s in self.data["theory"] if s["substation"] == module["id"]]
            self.assertGreaterEqual(len(sections), 4)
            self.assertEqual(sections[-1]["blocks"][-1]["type"], "note")
            self.assertIn("Контрольная точка", sections[-1]["blocks"][-1]["html"])
            self.assertEqual(len(self.resolved["checkpoints"][module["id"]]), 5)

    def test_self_checks_and_sources_per_section(self):
        for section in self.data["theory"]:
            with self.subTest(section=section["id"]):
                checks = [b for b in section["blocks"] if b["type"] == "self-check"]
                self.assertEqual(len(checks), 1)
                self.assertGreater(len(checks[0]["answer"]), 150)
                self.assertTrue(any("Первичные источники" in b.get("html", "")
                                    and "https://" in b["html"] for b in section["blocks"]))

    def test_final_banks_cover_route(self):
        for kind, minimum in (("basic", 32), ("advanced", 24), ("interview", 16)):
            bank = self.data["quizzes"][kind]
            self.assertGreaterEqual(len(bank), minimum)
            for module in self.data["substations"]:
                count = sum(q["substation"] == module["id"] for q in bank)
                self.assertGreaterEqual(count, 2)

    def test_no_repeated_question_stems(self):
        questions = [q for bank in self.data["quizzes"].values() for q in bank]
        questions += [q for bank in self.resolved["checkpoints"].values() for q in bank]
        stems = [normalize_prompt(q["q"]) for q in questions]
        self.assertEqual(len(stems), len(set(stems)))

    def test_options_are_not_uniform_length_hints(self):
        # A structural heuristic, not a substitute for editorial review.
        for kind, bank in self.data["quizzes"].items():
            for direction in ("longest", "shortest"):
                count = 0
                for q in bank:
                    n = len(q["options"][q["answer"]])
                    others = [len(s) for i, s in enumerate(q["options"]) if i != q["answer"]]
                    count += n > max(others) if direction == "longest" else n < min(others)
                self.assertLessEqual(count / len(bank), .5, (kind, direction, count))

    def test_real_practice_coverage(self):
        self.assertEqual(len(self.data["tasks"]), 10)
        analytic = {
            0: ("Разбор сценария: от намерения к наблюдению",
                "715de59731b0027a86ce5d9144d6e3b1ecdba6247762f6f69eebd9b1a37bc3e5"),
            4: ("Разбор сценария: таблица жизни данных",
                "5885ee535fbcf221aef740f8cf7a52240b06510339802c2154c18a2b02e71882"),
            5: ("Разбор сценария: выпуск без свободного места",
                "c2076e19e692bd96a8adb495c138502dade449927cce7c42af45df3f1eadba49"),
        }
        practice = [t for t in self.data["tasks"] if t["level"] == "Практика"
                    and t["title"].startswith("Лаборатория: ")]
        self.assertEqual(len(practice), 7)
        self.assertEqual([i for i, t in enumerate(self.data["tasks"])
                          if t["level"] != "Практика"], list(analytic))
        for index, (title, checksum) in analytic.items():
            task = self.data["tasks"][index]
            self.assertEqual(task["level"], "Разбор")
            self.assertEqual(task["title"], title)
            payload = {k: v for k, v in task.items() if k not in ("level", "title")}
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False,
                                               sort_keys=True).encode()).hexdigest()
            self.assertEqual(digest, checksum, "routing must not discard or rewrite the exercise")
        for task in self.data["tasks"]:
            self.assertGreaterEqual(len(task["checks"]), 3)
            self.assertGreater(len(task["solution"]), 220)

    def test_html_is_balanced_and_lab_link_exists(self):
        for section in self.data["theory"]:
            for block in section["blocks"]:
                for fragment in ([block["html"]] if "html" in block else []):
                    parser = Fragment()
                    parser.feed(fragment)
                    self.assertEqual(parser.stack, [], section["id"])
                    for href in re.findall(r'href="([^"]+)"', fragment):
                        if href.startswith("examples/"):
                            self.assertTrue((ROOT / "roadmap" / href).is_file(), href)

    def test_primary_sources_cover_sections(self):
        self.assertEqual(set(PRIMARY_SOURCES), {s["id"] for s in self.data["theory"]})
        for section in self.data["theory"]:
            with self.subTest(section=section["id"]):
                source_notes = [b["html"] for b in section["blocks"]
                                if b["type"] == "note"
                                and "Первичные источники" in b.get("html", "")]
                self.assertTrue(source_notes, "missing an explicit primary-source note")
                links = {url for note in source_notes
                         for url in re.findall(r'href="(https://[^"]+)"', note)}
                expected = {path if path.startswith("https://") else K8S_DOCS + path
                            for path in PRIMARY_SOURCES[section["id"]]}
                self.assertFalse(expected - links, "missing concrete primary documents: "
                                 + repr(sorted(expected - links)))

    def test_offline_manifest_contract(self):
        spec = importlib.util.spec_from_file_location("course13_verify", LAB / "verify.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        report = module.check_files()
        self.assertIn("NOT CHECKED", report[-1])
        readme = (LAB / "README.txt").read_text()
        cleanup_commands = [line.strip() for line in readme.splitlines()
                            if line.strip().startswith("kind delete cluster")]
        self.assertEqual(cleanup_commands, [
            "kind delete cluster --name course-station13-v1 --kubeconfig ./course13.kubeconfig"])
        self.assertNotIn("НЕ запускались в Kubernetes", readme)
        self.assertIn("30.10.2026", readme)
        warning = readme.index("ВАЖНО: kind v0.33.0 запускает узел как привилегированный контейнер")
        self.assertLess(warning, readme.index("  kind create cluster"))
        self.assertIn("Если такой доступ не разрешён, не создавай кластер", readme)
        self.assertIn("https://github.com/kubernetes-sigs/kind/blob/v0.33.0/"
                      "pkg/cluster/internal/providers/docker/provision.go#L202-L225", readme)
        # Creation's private kubeconfig does not implicitly select deletion's
        # path: kind0.33 delete --help documents its own --kubeconfig flag.
        for section in self.data["theory"]:
            for block in section["blocks"]:
                for line in block.get("code", "").splitlines():
                    if re.search(r"\bkind\s+delete\s+cluster\b", line):
                        self.assertIn("--kubeconfig", line, section["id"])

    def test_documented_math(self):
        self.assertEqual(3 / .75, 4)
        self.assertEqual(math.ceil(4 * 90 / 60), 6)
        self.assertEqual(18 - 6 - 9 - 4, -1)
        self.assertEqual(2 * 100, 200)
        self.assertEqual(3 * 64, 192)

    def test_installation_route_is_explicit_and_keeps_tools_local(self):
        section = next(s for s in self.data["theory"] if s["id"] == "lab-route")
        text = " ".join(b.get("html", "") for b in section["blocks"])
        self.assertIn("не устанавливает Docker", text)
        self.assertIn("README, раздел «Как получить инструменты»", text)
        self.assertIn("docker version", " ".join(b.get("code", "")
                                                  for b in section["blocks"]))
        readme = (LAB / "README.txt").read_text()
        self.assertLess(readme.index("Как получить инструменты"),
                        readme.index("0. Самая безопасная часть"))
        start = readme.index("  (\n")
        end = readme.index("  )\n", start) + len("  )\n")
        script = textwrap.dedent(readme[start:end])
        subprocess.run(["sh", "-n"], input=script, text=True, check=True)
        self.assertIn("set -eu", script)
        self.assertIn("test ! -e .course13-tools", script)
        self.assertIn("v0.33.0", script)
        self.assertIn("v1.36.4", script)
        self.assertEqual(script.count("sha256sum --check"), 2)
        self.assertNotIn("sudo", script)
        self.assertNotIn("/usr/", script)
        self.assertNotIn("create cluster", script)
        self.assertNotIn("rm ", script)
        self.assertIn(".course13-tools/", (LAB / ".gitignore").read_text())
        # Existing directories are refused before the first download, and the
        # refusal does not remove or modify their contents. No network needed.
        with tempfile.TemporaryDirectory(prefix="course13-setup-refusal-") as tmp:
            folder = Path(tmp) / ".course13-tools"
            folder.mkdir()
            sentinel = folder / "keep.txt"
            sentinel.write_text("existing user file")
            result = subprocess.run(["sh"], input=script, text=True, cwd=tmp,
                                    capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(), "existing user file")
            self.assertEqual([p.name for p in folder.iterdir()], ["keep.txt"])

    def test_pinned_httplib_threadpool_arguments(self):
        # In0.59.0 the second argument is maximum threads, not queue capacity.
        # A two-argument (4,16) constructor would leave its third mqr=0 unbounded.
        app = (LAB / "app.cpp").read_text()
        self.assertRegex(app, r"httplib::ThreadPool\(4,\s*4,\s*16\)")
        self.assertNotRegex(app, r"httplib::ThreadPool\(4,\s*16\)")

    def test_full_model_matches_workbook(self):
        section = next(s for s in self.data["theory"] if s["id"] == "kubernetes-final-workbook")
        codes = [b["code"] for b in section["blocks"] if b["type"] == "code"]
        self.assertEqual(codes[0], (LAB / "drain_model.cpp").read_text().rstrip())
        self.assertEqual(codes[1], "first accepted: true\nready: false\nsecond accepted: false\n"
                                  "stopped before finish: false\nstopped after finish: true")

    @unittest.skipUnless(shutil.which("g++"), "g++ unavailable: model not compiled")
    def test_cpp_model_runs_offline(self):
        with tempfile.TemporaryDirectory(prefix="course13-model-") as tmp:
            exe = Path(tmp) / "model"
            subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Wpedantic",
                            str(LAB / "drain_model.cpp"), "-o", str(exe)], check=True, timeout=60)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "first accepted: true\nready: false\nsecond accepted: false\n"
                                       "stopped before finish: false\nstopped after finish: true\n")

    @unittest.skipUnless(shutil.which("g++") and os.environ.get("COURSE_HTTPLIB_INCLUDE"),
                         "set COURSE_HTTPLIB_INCLUDE to verified0.59.0 header for offline app build")
    def test_http_binary_self_test_without_listener(self):
        include = Path(os.environ["COURSE_HTTPLIB_INCLUDE"])
        header = (include / "httplib.h").read_text()
        self.assertRegex(header, r'CPPHTTPLIB_VERSION\s+"0\.59\.0"')
        with tempfile.TemporaryDirectory(prefix="course13-http-") as tmp:
            exe = Path(tmp) / "server"
            subprocess.run(["g++", "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra",
                            "-Wpedantic", "-I", str(include), str(LAB / "app.cpp"),
                            "-o", str(exe)], check=True, timeout=60)
            result = subprocess.run([str(exe), "--self-test"], check=True,
                                    capture_output=True, text=True, timeout=5)
        self.assertEqual(result.stdout, "admission/drain self-test passed\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
