import tempfile
import unittest
from pathlib import Path

from astrbot_plugin_multisim.application.path_policy import WorkspacePathPolicy
from astrbot_plugin_multisim.application.simulation_service import SimulationService
from astrbot_plugin_multisim.config import PluginSettings
from astrbot_plugin_multisim.domain.errors import PermissionDenied
from astrbot_plugin_multisim.infrastructure.fake_backend import FakeBackend


class SimulationServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "workspace"
        self.root.mkdir()
        self.policy = WorkspacePathPolicy(self.root)
        self.backend = FakeBackend(job_terminal_after=1)
        self.settings = PluginSettings()
        self.service = SimulationService(self.backend, self.settings, self.policy)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_status(self):
        payload = await self.service.status()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tool_count"], len(await self.backend.list_tools()))
        self.assertIn("runtime_status", payload["tool_map"])
        self.assertTrue(payload["runtime"]["ok"])
        self.assertTrue(payload["multisim_ready"])

    async def test_status_reports_introspection_only(self):
        # 直接在假后端上覆写 runtime_status 的返回值
        def handler(args):
            from astrbot_plugin_multisim.domain.models import BackendReply

            return BackendReply(
                tool="runtime_status",
                ok=True,
                data={
                    "runtime_mode": "introspection-only",
                    "runtime_compatible": False,
                    "required_python_bits": 32,
                },
            )

        self.backend._tool_runtime_status = handler  # type: ignore[assignment]
        payload = await self.service.status()
        self.assertFalse(payload["multisim_ready"])
        self.assertEqual(payload["runtime_mode"], "introspection-only")

    async def test_submit_and_get_job(self):
        submitted = await self.service.submit_experiment(
            {"netlist": "R1 in out 1k\nC1 out 0 1u", "commands": "tran 0 1m"}
        )
        self.assertTrue(submitted["ok"], submitted)
        job_id = submitted["job_id"]
        self.assertTrue(job_id.startswith("fake-job-"))

        snapshot = await self.service.get_job(job_id)
        self.assertTrue(snapshot["ok"])
        self.assertEqual(snapshot["state"], "succeeded")
        self.assertEqual(snapshot["verification"], "pass")

        summary = await self.service.get_summary(job_id)
        self.assertTrue(summary["ok"])

    async def test_output_dir_is_created_inside_workspace(self):
        submitted = await self.service.submit_experiment(
            {"netlist": "...", "output_dir": "runs/demo1"}
        )
        self.assertTrue(submitted["ok"], submitted)
        self.assertTrue((self.root / "runs" / "demo1").is_dir())

    async def test_output_dir_outside_workspace_rejected(self):
        with self.assertRaises(PermissionDenied):
            await self.service.submit_experiment(
                {"netlist": "..."}, output_dir="../outside"
            )

    async def test_verified_wraps_spec(self):
        submitted = await self.service.submit_experiment(
            {"netlist": "...", "requirements": []}, verified=True
        )
        self.assertTrue(submitted["ok"], submitted)
        tool, args = self.backend.calls[-1]
        self.assertEqual(tool, "run_verified_circuit_experiment")
        self.assertIn("spec", args)

    async def test_spice_and_save_forwarded(self):
        spice = await self.service.run_spice({"commands": "tran 0 1m"})
        self.assertTrue(spice["ok"], spice)
        self.assertEqual(self.backend.calls[-1][0], "run_spice_netlist")

        saved = await self.service.save_circuit({"path": "out.ms14"})
        self.assertTrue(saved["ok"], saved)
        self.assertEqual(self.backend.calls[-1][0], "save_circuit_as")

    async def test_component_edit_toggle(self):
        payload = await self.service.set_component_value("R1", 2200.0)
        self.assertTrue(payload["ok"], payload)

        self.settings.allow_component_edit = False
        with self.assertRaises(PermissionDenied):
            await self.service.set_component_value("R1", 2200.0)

    async def test_sweep_toggle(self):
        payload = await self.service.run_sweep({"param": "R1", "values": [1, 2]})
        self.assertTrue(payload["ok"], payload)

        self.settings.allow_sweep = False
        with self.assertRaises(PermissionDenied):
            await self.service.run_sweep({"param": "R1", "values": [1, 2]})

    async def test_open_circuit_requires_existing_file(self):
        target = self.root / "rc.ms14"
        target.write_text("dummy", encoding="utf-8")
        payload = await self.service.open_circuit("rc.ms14")
        self.assertTrue(payload["ok"], payload)
        tool, args = self.backend.calls[-1]
        self.assertEqual(tool, "open_circuit_file")
        self.assertEqual(Path(args["path"]), target.resolve())

    async def test_stop_cancels_active_jobs(self):
        await self.service.submit_experiment({"netlist": "..."})
        result = await self.service.stop()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["cancelled"]), 1)

    async def test_unknown_tool_surfaces_structured_error(self):
        # 上游只暴露 runtime_status 时，原生工具应报 tool_unavailable
        self.backend.list_tools = self._only_runtime_status
        self.service._toolmap = None
        payload = await self.service.list_components()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["code"], "tool_unavailable")

    async def _only_runtime_status(self):
        return ["runtime_status"]


if __name__ == "__main__":
    unittest.main()
