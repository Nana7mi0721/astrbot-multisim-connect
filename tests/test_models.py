import unittest

from astrbot_plugin_multisim.domain.models import (
    BackendReply,
    JobState,
    VerificationStatus,
)


class JobStateTest(unittest.TestCase):
    def test_parse_known_states(self):
        self.assertIs(JobState.parse("running"), JobState.RUNNING)
        self.assertIs(JobState.parse("SUCCEEDED"), JobState.SUCCEEDED)
        self.assertIs(JobState.parse("timed_out"), JobState.TIMED_OUT)

    def test_parse_aliases(self):
        self.assertIs(JobState.parse("completed"), JobState.SUCCEEDED)
        self.assertIs(JobState.parse("error"), JobState.FAILED)
        self.assertIs(JobState.parse("pending"), JobState.QUEUED)

    def test_parse_unknown(self):
        self.assertIs(JobState.parse("weird"), JobState.UNKNOWN)
        self.assertIs(JobState.parse(None), JobState.UNKNOWN)

    def test_terminal(self):
        self.assertTrue(JobState.SUCCEEDED.terminal)
        self.assertTrue(JobState.FAILED.terminal)
        self.assertFalse(JobState.RUNNING.terminal)
        self.assertFalse(JobState.QUEUED.terminal)


class VerificationStatusTest(unittest.TestCase):
    def test_parse(self):
        self.assertIs(VerificationStatus.parse("PASS"), VerificationStatus.PASS)
        self.assertIs(VerificationStatus.parse("unverified"), VerificationStatus.UNVERIFIED)
        self.assertIsNone(VerificationStatus.parse(None))
        self.assertIsNone(VerificationStatus.parse("something-else"))


class BackendReplyTest(unittest.TestCase):
    def test_defaults(self):
        reply = BackendReply(tool="x", ok=True, data={"a": 1})
        self.assertTrue(reply.ok)
        self.assertFalse(reply.retryable)


if __name__ == "__main__":
    unittest.main()
