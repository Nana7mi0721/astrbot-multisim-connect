import unittest
from typing import Any

from astrbot_plugin_multisim.application.job_service import JobService


class ScriptedInvoker:
    """按 key 返回脚本化响应的 invoke 桩。"""

    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, key: str, args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((key, dict(args)))
        return await self.handler(key, args)


class JobServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_submit_records_job(self):
        async def handler(key, args):
            return {
                "ok": True,
                "tool": "submit_circuit_experiment",
                "data": {"job_id": "j1", "state": "queued"},
            }

        service = JobService(ScriptedInvoker(handler), poll_s=0.01, timeout_s=1)
        result = await service.submit("submit_experiment", {"netlist": "..."})
        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "j1")
        self.assertEqual(result["state"], "queued")
        self.assertEqual(await service.active_ids(), ["j1"])
        self.assertEqual((await service.recent())[0]["job_id"], "j1")

    async def test_submit_without_job_id_raises(self):
        async def handler(key, args):
            return {"ok": True, "tool": "x", "data": {"state": "queued"}}

        service = JobService(ScriptedInvoker(handler))
        from astrbot_plugin_multisim.domain.errors import SimulationFailed

        with self.assertRaises(SimulationFailed):
            await service.submit("submit_experiment", {})

    async def test_wait_until_terminal(self):
        polls = {"n": 0}

        async def handler(key, args):
            if key == "submit_experiment":
                return {"ok": True, "tool": "t", "data": {"job_id": "j1", "state": "queued"}}
            polls["n"] += 1
            state = "succeeded" if polls["n"] >= 2 else "running"
            return {
                "ok": True,
                "tool": "get_experiment_job",
                "data": {"job_id": "j1", "state": state, "verification": "pass"},
            }

        service = JobService(ScriptedInvoker(handler), poll_s=0.01, timeout_s=1)
        await service.submit("submit_experiment", {})
        result = await service.wait("j1", poll_s=0.01, timeout_s=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "succeeded")
        self.assertEqual(result["verification"], "pass")
        self.assertEqual(await service.active_ids(), [])

    async def test_wait_timeout(self):
        async def handler(key, args):
            return {
                "ok": True,
                "tool": "get_experiment_job",
                "data": {"job_id": "j2", "state": "running"},
            }

        service = JobService(ScriptedInvoker(handler), poll_s=0.01, timeout_s=1)
        result = await service.wait("j2", poll_s=0.01, timeout_s=0.05)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "timeout")
        self.assertTrue(result["retryable"])

    async def test_invalid_input_fallback_to_experiment_id(self):
        async def handler(key, args):
            if "job_id" in args:
                return {"ok": False, "code": "invalid_input", "message": "unknown field"}
            return {
                "ok": True,
                "tool": "get_experiment_job",
                "data": {"job_id": "j3", "state": "succeeded"},
            }

        invoker = ScriptedInvoker(handler)
        service = JobService(invoker, poll_s=0.01, timeout_s=1)
        result = await service.get("j3")
        self.assertTrue(result["ok"])
        self.assertEqual(invoker.calls[-1][1], {"experiment_id": "j3"})

    async def test_error_passthrough(self):
        async def handler(key, args):
            return {"ok": False, "code": "not_found", "message": "任务不存在", "job_id": "j4"}

        service = JobService(ScriptedInvoker(handler))
        result = await service.get("j4")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "not_found")
        self.assertEqual(result["job_id"], "j4")

    async def test_cancel_updates_state(self):
        async def handler(key, args):
            if key == "submit_experiment":
                return {"ok": True, "tool": "t", "data": {"job_id": "j5", "state": "queued"}}
            return {
                "ok": True,
                "tool": "cancel_experiment_job",
                "data": {"job_id": "j5", "state": "cancelled"},
            }

        service = JobService(ScriptedInvoker(handler), poll_s=0.01, timeout_s=1)
        await service.submit("submit_experiment", {})
        result = await service.cancel("j5")
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "cancelled")
        self.assertEqual(await service.active_ids(), [])


if __name__ == "__main__":
    unittest.main()
