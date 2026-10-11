import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.robot_network import ROBOT_HOSTS, resolve_config, robot_host


class RobotNetworkTests(unittest.TestCase):
    def setUp(self):
        robot_host.cache_clear()
        self.env = patch.dict(os.environ, {"ROVE_ROBOT_HOST": "auto"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        robot_host.cache_clear()

    def probe(self, reachable):
        def open_url(url, timeout):
            if any(f"//{host}:" in url for host in reachable):
                return io.BytesIO(b'{"sensors": []}')
            raise OSError("unreachable")
        return Mock(open=Mock(side_effect=open_url))

    def test_selects_each_network_and_caches_for_all_windows(self):
        for host in ROBOT_HOSTS:
            robot_host.cache_clear()
            with patch("src.robot_network.build_opener", return_value=self.probe([host])) as build:
                self.assertEqual(robot_host(), host)
                self.assertEqual(robot_host(), host)
                build.assert_called_once()

    def test_prefers_current_subnet_if_both_addresses_respond(self):
        with patch("src.robot_network.build_opener", return_value=self.probe(ROBOT_HOSTS)), patch(
            "src.robot_network._direct_route", side_effect=lambda host: host == "192.168.1.2"
        ):
            self.assertEqual(robot_host(), "192.168.1.2")

    def test_ambiguous_and_missing_robot_fail_before_controls_start(self):
        for hosts in [ROBOT_HOSTS, []]:
            robot_host.cache_clear()
            with patch("src.robot_network.build_opener", return_value=self.probe(hosts)), patch(
                "src.robot_network._direct_route", return_value=False
            ):
                with self.assertRaises(ValueError):
                    robot_host()

    def test_explicit_host_does_not_probe(self):
        with patch.dict(os.environ, {"ROVE_ROBOT_HOST": "192.168.1.2"}), patch(
            "src.robot_network.build_opener"
        ) as build:
            self.assertEqual(robot_host(), "192.168.1.2")
            build.assert_not_called()

    def test_controls_missions_estop_and_sensors_share_robot_host(self):
        config = json.loads((Path(__file__).resolve().parents[1] / "config/config_window1.json").read_text())
        for host in ROBOT_HOSTS:
            resolved = resolve_config(config, host)
            self.assertNotIn("${ROBOT_HOST}", json.dumps(resolved))
            teleop = resolved["views"]["INPUT MANAGER"]["content"][0]["data"]
            self.assertEqual((teleop["host"], teleop["port"]), (host, 5050))
            mission = next(c for c in resolved["http_clients"] if c["name"] == "send_mission")
            self.assertEqual((mission["host"], mission["port"]), (host, 5051))
            estop = next(c for c in resolved["http_clients"] if c["name"] == "odrive_estop")
            self.assertEqual(estop["base_url"], f"http://{host}:8080")
            self.assertIn("192.168.2.31", json.dumps(resolved))
            self.assertIn("192.168.2.3:8888", json.dumps(resolved))


if __name__ == "__main__":
    unittest.main()
