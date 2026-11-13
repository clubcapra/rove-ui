import unittest
from unittest.mock import Mock, patch

from src.clients.mission_client import MissionClient
from src.proto_gen.proto.Mission_pb2 import Mission, MissionResult


class MissionClientTests(unittest.TestCase):
    def test_sends_raw_protobuf_and_reads_bridge_ack(self):
        bus = Mock()
        client = MissionClient({"host": "192.168.1.2", "port": 5051}, bus)
        sock = Mock()
        sock.recv.return_value = MissionResult(status=MissionResult.ACCEPTED).SerializeToString()
        with patch("src.clients.mission_client.socket.socket") as factory:
            factory.return_value.__enter__.return_value = sock
            client._send({"name": "test", "sequence": [{"command": "GoTo", "params": [
                {"name": "coordinate", "value": {"coordinate": {"lat": 46.7, "lon": 7.5}}}
            ], "transition": {"type": "UNTIL_DONE_NEXT"}}]})
        sock.connect.assert_called_once_with(("192.168.1.2", 5051))
        decoded = Mission.FromString(sock.send.call_args.args[0])
        self.assertEqual(decoded.name, "test")
        self.assertEqual(decoded.sequence[0].params[0].value.coordinate.lat, 46.7)
        self.assertIn("ACCEPTED", bus.publish_sync.call_args.args[1])

    def test_stop_removes_mission_subscription(self):
        bus = Mock()
        client = MissionClient({"host": "192.168.2.2"}, bus)
        client.start()
        client.stop()
        bus.unsubscribe.assert_called_once_with("mission.send", client._on_event)


if __name__ == "__main__":
    unittest.main()
