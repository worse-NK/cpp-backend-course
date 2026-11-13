#!/usr/bin/env python3
"""Launcher file guards, no Docker and no network beyond an unused loopback bind."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import lab


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="course-path-unit-")
        self.root = Path(self.directory.name)
        self.port = 18089
        self.socket_mock = mock.patch.object(lab.socket, "socket")
        self.socket_mock.start()  # This unit suite tests files; integration binds real sockets.

    def tearDown(self):
        self.socket_mock.stop()
        self.directory.cleanup()

    def test_init_and_roundtrip_without_secret_output(self):
        expected = lab.init(self.port, self.root)
        self.assertEqual(lab.configuration(self.root), expected)
        self.assertEqual(stat.S_IMODE((self.root / ".state").stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / ".state/settings.json").stat().st_mode), 0o600)
        passwords = [lab.read_private(name + "_password", root=self.root).strip() for name in lab.SECRET_NAMES]
        self.assertEqual(len(set(passwords)), len(lab.SECRET_NAMES))
        self.assertTrue(all(lab.HEX.fullmatch(value) for value in passwords))

    def test_second_init_does_not_overwrite(self):
        expected = lab.init(self.port, self.root)
        with self.assertRaises(FileExistsError):
            lab.init(self.port, self.root)
        self.assertEqual(lab.configuration(self.root), expected)

    def test_directory_symlink_refused(self):
        other = self.root / "other"
        other.mkdir(mode=0o700)
        (self.root / ".state").symlink_to(other, target_is_directory=True)
        with self.assertRaises(OSError):
            lab.configuration(self.root)

    def test_secret_symlink_refused(self):
        lab.init(self.port, self.root)
        target = self.root / ".state/api_password"
        target.unlink()
        target.symlink_to("admin_password")
        with self.assertRaises(OSError):
            lab.configuration(self.root)

    def test_hardlink_secret_refused(self):
        lab.init(self.port, self.root)
        os.link(self.root / ".state/api_password", self.root / "extra_link")
        with self.assertRaises(ValueError):
            lab.configuration(self.root)

    def test_wrong_directory_permissions_refused(self):
        lab.init(self.port, self.root)
        (self.root / ".state").chmod(0o755)
        with self.assertRaises(ValueError):
            lab.configuration(self.root)

    def test_arbitrary_project_refused(self):
        lab.init(self.port, self.root)
        path = self.root / ".state/settings.json"
        data = json.loads(path.read_text())
        data["project"] = "existing-project"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            lab.configuration(self.root)

    def test_boolean_version_is_not_integer_schema_version(self):
        lab.init(self.port, self.root)
        path = self.root / ".state/settings.json"
        data = json.loads(path.read_text())
        data["version"] = True
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            lab.configuration(self.root)

    def test_compose_environment_does_not_inherit_project_override(self):
        config = lab.init(self.port, self.root)
        previous = os.environ.get("COMPOSE_PROJECT_NAME")
        os.environ["COMPOSE_PROJECT_NAME"] = "unrelated"
        try:
            env = lab.environment(config)
            self.assertNotIn("COMPOSE_PROJECT_NAME", env)
            self.assertEqual(env["PATH_PROJECT"], config["project"])
            self.assertFalse(any(key.endswith("PASSWORD") for key in env if key.startswith("PATH_")))
        finally:
            if previous is None:
                os.environ.pop("COMPOSE_PROJECT_NAME", None)
            else:
                os.environ["COMPOSE_PROJECT_NAME"] = previous


if __name__ == "__main__":
    unittest.main()
