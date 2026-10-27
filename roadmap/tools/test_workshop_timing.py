"""Per-response timing on an explicitly supplied, freshly built owned server.

Set WORKSHOP_TIMING_BINARY; socket restrictions skip, never pretend HTTP passed.
"""
import concurrent.futures
import os
from pathlib import Path
import re
import secrets
import unittest

import verify_service_workshop as verify


@unittest.skipUnless(os.environ.get("WORKSHOP_TIMING_BINARY"),
                     "set WORKSHOP_TIMING_BINARY to run real owned HTTP timing checks")
class WorkshopTiming(unittest.TestCase):
    def test_timing_is_response_scoped_and_does_not_disclose_inputs(self):
        try:
            server = verify.NativeServer(Path(os.environ["WORKSHOP_TIMING_BINARY"]), secrets.token_hex(32))
        except verify.NetworkUnavailable as error:
            self.skipTest(str(error))
        try:
            server.start()
            client = server.client
            private_title = "private-teaching-title-never-log"
            verify.create_task(client, private_title)

            def read(index):
                if index % 3 == 0:
                    return client.request("GET", "/tasks", authorization=client.wrong_token).status
                return client.request("GET", "/tasks").status

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                statuses = list(executor.map(read, range(36)))
            self.assertEqual(statuses.count(401), 12)
            self.assertEqual(statuses.count(200), 24)
            self.assertEqual(client.request("POST", "/tasks", b"not-json").status, 400)
            self.assertEqual(client.request("GET", "/health/live", authorization=None).status, 200)
            self.assertEqual(client.request("GET", "/private-path-never-log?secret=private-query-never-log").status, 404)
            server.stop()
            server.check_logs()
            data = "\n".join(path.read_text() for path in server.log_paths)
            for private in (private_title, "private-path-never-log", "private-query-never-log"):
                self.assertNotIn(private, data)
            rows = re.findall(r"request method=(\S+) path=(\S+) status=(\d+) "
                              r"handler_us=(\d+|not_measured) storage_us=(\d+|not_measured)", data)
            self.assertGreaterEqual(len(rows), 41)
            unauthenticated = [row for row in rows if row[2] == "401"]
            self.assertEqual(len(unauthenticated), 12)
            self.assertTrue(all(row[3:] == ("not_measured", "not_measured") for row in unauthenticated))
            for _, _, _, handler, storage in rows:
                if handler != "not_measured":
                    self.assertGreaterEqual(int(handler), int(storage))
            bad_input = [row for row in rows if row[2] == "400"]
            self.assertTrue(bad_input)
            self.assertTrue(all(row[3].isdigit() and row[4] == "0" for row in bad_input))
            live = [row for row in rows if row[1] == "/health/live"]
            self.assertTrue(live)
            self.assertTrue(all(row[3].isdigit() and row[4] == "0" for row in live))
            self.assertEqual(server.exit_codes, [0])
            self.assertFalse(server.forced_shutdown)
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
