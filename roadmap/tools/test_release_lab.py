"""Offline source/safety checks; live PostgreSQL execution is opt-in separately."""
import importlib.util
import os
from pathlib import Path
import re
import stat
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "examples/service-workshop/release-lab"
spec = importlib.util.spec_from_file_location("course_release_lab_helper", LAB / "release_lab.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ReleaseLabSafety(unittest.TestCase):
    def test_init_has_unique_project_independent_secrets_and_private_mode(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            paths = [Path(first), Path(second)]
            for path in paths:
                helper.init(path)
                self.assertEqual(stat.S_IMODE((path / ".env").stat().st_mode), 0o600)
            a, b = [helper.read_env(path) for path in paths]
            self.assertNotEqual(a["RELEASE_LAB_PROJECT"], b["RELEASE_LAB_PROJECT"])
            self.assertNotEqual(a["APP_DB_PASSWORD"], a["POSTGRES_PASSWORD"])
            self.assertNotEqual(a["APP_DB_PASSWORD"], b["APP_DB_PASSWORD"])

    def test_init_refuses_existing_file_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            helper.init(path)
            before = (path / ".env").read_bytes()
            with self.assertRaises(FileExistsError):
                helper.init(path)
            self.assertEqual((path / ".env").read_bytes(), before)

    def test_env_rejects_symlink_hardlink_wrong_mode_and_unknown_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            helper.init(path)
            settings = path / ".env"
            settings.chmod(0o644)
            with self.assertRaises(ValueError):
                helper.read_env(path)
            settings.chmod(0o600)
            os.link(settings, path / "duplicate")
            with self.assertRaises(ValueError):
                helper.read_env(path)
            (path / "duplicate").unlink()
            content = settings.read_text()
            settings.write_text(content + "DOCKER_HOST=untrusted\n")
            with self.assertRaises(ValueError):
                helper.read_env(path)
            settings.rename(path / "original")
            settings.symlink_to(path / "original")
            with self.assertRaises(OSError):
                helper.read_env(path)

    def test_schema_owner_and_expand_are_atomic_and_app_is_not_ddl_owner(self):
        initial = (LAB / "001-initial.sql").read_text()
        expand = (LAB / "002-expand-note.sql").read_text()
        self.assertIn("CREATE ROLE release_owner NOLOGIN", initial)
        self.assertIn("CREATE ROLE release_app LOGIN PASSWORD :'app_password'", initial)
        self.assertIn("AUTHORIZATION release_owner", initial)
        for sql in (initial, expand):
            self.assertEqual(sql.count("BEGIN;"), 1)
            self.assertEqual(sql.count("COMMIT;"), 1)
            self.assertIn("SET LOCAL ROLE release_owner;", sql)
            self.assertNotRegex(sql, r"\bDROP\s+(TABLE|COLUMN|DATABASE)\b")
            self.assertNotIn("IF NOT EXISTS", sql)
        self.assertIn("ADD COLUMN note text", expand)
        self.assertIn("GRANT SELECT (note), UPDATE (note)", expand)
        self.assertIn("SET LOCAL lock_timeout", expand)
        self.assertIn("SET LOCAL statement_timeout", expand)

    def test_two_real_binaries_and_named_column_update_not_row_replacement(self):
        cmake = (LAB / "CMakeLists.txt").read_text()
        source = (LAB / "client.cpp").read_text()
        self.assertIn("foreach(release_version 1 2)", cmake)
        self.assertIn("RELEASE_VERSION=${release_version}", cmake)
        self.assertIn('"id,title,version,note"', source)
        self.assertIn('"id,title,version"', source)
        self.assertIn("pqxx::params{value, expected}", source)
        self.assertIn("version=$2", source)
        self.assertIn("version<9223372036854775807", source)
        self.assertIn("tx.commit();\n    print(task)", source)
        self.assertNotIn("SELECT *", source)
        self.assertNotIn("REPLACE INTO", source)
        self.assertNotIn("DELETE FROM", source)

    def test_public_configuration_has_no_ports_and_has_resource_and_ownership_bounds(self):
        compose = (LAB / "compose.yaml").read_text()
        self.assertNotRegex(compose, r"(?m)^\s+ports:")
        self.assertIn("internal: true", compose)
        self.assertIn("profiles: [tools]", compose)
        self.assertIn("org.cpp-backend-course.release-lab", compose)
        self.assertIn('cpus: "1.0"', compose)
        self.assertIn("mem_limit: 512m", compose)
        self.assertIn("pids_limit: 128", compose)
        self.assertIn('tmpfs: ["/tmp:rw,noexec,nosuid,size=8m"]', compose)
        self.assertIn(".env", (LAB / ".dockerignore").read_text().splitlines())
        self.assertIn(".env", (LAB / ".gitignore").read_text().splitlines())

    def test_chapter_has_complete_states_and_truthful_scope(self):
        text = (ROOT / "content/service-workshop/release.html").read_text()
        self.assertEqual(len(re.findall(r"<h2>", text)), 7)
        for phrase in ("Original", "Before expand", "Keep this note", "Edited by old version",
                       "Rollback stays compatible", "Forward again", "Must not appear"):
            self.assertIn(phrase, text)
        self.assertIn("нет HTTP-сервера", text)
        self.assertIn("Смешанное окно", text)
        self.assertIn("код выхода 2", text)
        self.assertIn("проверка возврата программы", text)
        self.assertIn("не включает", text)
        for filename in ("README.md", "client.cpp", "002-expand-note.sql"):
            self.assertIn("examples/service-workshop/release-lab/" + filename, text)


if __name__ == "__main__":
    unittest.main()
