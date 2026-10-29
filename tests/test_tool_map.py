import unittest

from astrbot_plugin_multisim.domain.errors import ToolUnavailable
from astrbot_plugin_multisim.infrastructure.tool_map import ToolMap

FAKE_TOOLS = [
    "runtime_status",
    "submit_circuit_experiment",
    "get_experiment_job",
    "open_circuit_file",
    "set_component_value",
    "list_components",
    "run_spice_netlist",
    "save_circuit_as",
]


# multisim-mcp 1.3.0 full profile 中的真实工具名（含易混淆的 getter/positions）
REAL_TOOLS = [
    "runtime_status",
    "submit_circuit_experiment",
    "run_verified_circuit_experiment",
    "get_experiment_job",
    "list_experiment_jobs",
    "cancel_experiment_job",
    "get_experiment_summary",
    "submit_experiment_sweep",
    "export_formal_experiment_report",
    "open_circuit",
    "snapshot_open_circuit",
    "enum_components",
    "list_component_positions",
    "set_rlc_value",
    "get_rlc_value",
    "save_circuit",
    "run_spice_netlist",
    "do_command_line",
]


class RealToolsDiscoveryTest(unittest.TestCase):
    def test_expected_bindings(self):
        toolmap = ToolMap(REAL_TOOLS)
        expected = {
            "open_circuit": "open_circuit",
            "set_component_value": "set_rlc_value",
            "list_components": "enum_components",
            "run_spice": "run_spice_netlist",
            "save_circuit": "save_circuit",
        }
        for key, tool in expected.items():
            self.assertEqual(toolmap.binding(key).backend_tool, tool, key)
        self.assertEqual(toolmap.missing(), [])


class ToolMapTest(unittest.TestCase):
    def test_default_binding_present(self):
        toolmap = ToolMap(FAKE_TOOLS)
        binding = toolmap.binding("runtime_status")
        self.assertTrue(binding.available)
        self.assertEqual(binding.backend_tool, "runtime_status")
        self.assertEqual(binding.source, "default")

    def test_discovery_of_native_tools(self):
        toolmap = ToolMap(FAKE_TOOLS)
        for key, expected in {
            "open_circuit": "open_circuit_file",
            "set_component_value": "set_component_value",
            "list_components": "list_components",
            "run_spice": "run_spice_netlist",
            "save_circuit": "save_circuit_as",
        }.items():
            binding = toolmap.binding(key)
            self.assertEqual(binding.backend_tool, expected, key)
            self.assertEqual(binding.source, "discovered", key)

    def test_config_override_wins(self):
        toolmap = ToolMap(FAKE_TOOLS, {"open_circuit": "my_open_tool"})
        binding = toolmap.binding("open_circuit")
        self.assertEqual(binding.backend_tool, "my_open_tool")
        self.assertEqual(binding.source, "config")

    def test_missing_tool_raises(self):
        toolmap = ToolMap(["runtime_status"])
        with self.assertRaises(ToolUnavailable):
            toolmap.require("open_circuit")
        self.assertIn("open_circuit", toolmap.missing())

    def test_unknown_available_list_keeps_defaults(self):
        toolmap = ToolMap([])
        self.assertEqual(toolmap.binding("runtime_status").backend_tool, "runtime_status")
        self.assertFalse(toolmap.binding("open_circuit").available)

    def test_report_shape(self):
        report = ToolMap(FAKE_TOOLS).report()
        self.assertIn("runtime_status", report)
        self.assertTrue(report["runtime_status"]["available"])


if __name__ == "__main__":
    unittest.main()
