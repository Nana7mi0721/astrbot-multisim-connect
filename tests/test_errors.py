import unittest

from astrbot_plugin_multisim.domain import errors


class ErrorMappingTest(unittest.TestCase):
    def test_known_codes(self):
        err = errors.from_backend_code("timeout", "too slow")
        self.assertIsInstance(err, errors.JobTimedOut)
        self.assertTrue(err.retryable)
        payload = err.to_dict()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "timeout")
        self.assertEqual(payload["message"], "too slow")

    def test_backend_unavailable_retryable(self):
        err = errors.from_backend_code("backend_unavailable")
        self.assertIsInstance(err, errors.BackendUnavailable)
        self.assertTrue(err.retryable)

    def test_unknown_code_preserved(self):
        err = errors.from_backend_code("permission_denied", "no")
        self.assertIsInstance(err, errors.PermissionDenied)
        self.assertFalse(err.retryable)

        weird = errors.from_backend_code("some_vendor_code", "boom")
        self.assertEqual(weird.code, "some_vendor_code")
        self.assertFalse(weird.retryable)

    def test_details_in_payload(self):
        err = errors.ToolUnavailable("missing", details={"key": "open_circuit"})
        payload = err.to_dict()
        self.assertEqual(payload["details"]["key"], "open_circuit")


if __name__ == "__main__":
    unittest.main()
