from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread
from typing import Any

from src.controller.event_bus import EventBus

try:
	import rclpy
	from rclpy.executors import SingleThreadedExecutor
	from rclpy.node import Node
	from rosidl_runtime_py.convert import message_to_ordereddict
	from rosidl_runtime_py.utilities import get_message

	ROS2_AVAILABLE = True
	ROS2_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on local ROS2 install
	rclpy = None  # type: ignore[assignment]
	SingleThreadedExecutor = None  # type: ignore[assignment]
	Node = Any  # type: ignore[assignment]
	message_to_ordereddict = None  # type: ignore[assignment]
	get_message = None  # type: ignore[assignment]
	ROS2_AVAILABLE = False
	ROS2_IMPORT_ERROR = exc


@dataclass(slots=True)
class ROS2TopicConfig:
	name: str
	msg_type: str = "std_msgs/msg/String"
	qos_depth: int = 10
	event_topic: str = ""
	transform: str = ""


@dataclass(slots=True)
class ROS2ClientConfig:
	name: str = "ros2_client"
	node_name: str = "capraui_ros2_bridge"
	topics: tuple[ROS2TopicConfig, ...] = ()
	enabled: bool = True
	event_prefix: str = ""
	spin_timeout_s: float = 0.1


class ROS2Client:
	def __init__(self, config: dict[str, Any], event_bus: EventBus | None = None):
		topics = tuple(self._parse_topics(config.get("topics", [])))
		self.config = ROS2ClientConfig(
			name=str(config.get("name", "ros2_client")),
			node_name=str(config.get("node_name", "capraui_ros2_bridge")),
			topics=topics,
			enabled=bool(config.get("enabled", True)),
			event_prefix=str(config.get("event_prefix", "")).strip("."),
			spin_timeout_s=max(0.01, float(config.get("spin_timeout_s", 0.1))),
		)
		self.event_bus = event_bus or EventBus()
		self.event_bus.publish_sync("log", f"ROS2 client '{self.config.name}' initialized with {len(self.config.topics)} topics")
		self._stop_event = Event()
		self._thread: Thread | None = None
		self._node: Any | None = None
		self._executor: Any | None = None
		self._subscriptions: list[Any] = []
		self._owns_rclpy_context = False

	def start(self) -> None:
		if not self.config.enabled or self._thread is not None:
			return

		if not ROS2_AVAILABLE or rclpy is None:
			self.event_bus.publish_sync(
				"log",
				f"ROS2 client '{self.config.name}' disabled: rclpy unavailable ({ROS2_IMPORT_ERROR})",
			)
			return

		if not self.config.topics:
			self.event_bus.publish_sync(
				"log",
				f"ROS2 client '{self.config.name}' has no topics configured",
			)
			return

		self._stop_event.clear()

		if not rclpy.ok():
			rclpy.init(args=None)
			self._owns_rclpy_context = True

		self._node = Node(self.config.node_name)
		self._executor = SingleThreadedExecutor()
		self._executor.add_node(self._node)

		for topic_cfg in self.config.topics:
			try:
				msg_cls = get_message(topic_cfg.msg_type)
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"ROS2 client '{self.config.name}' skipped topic '{topic_cfg.name}': invalid type '{topic_cfg.msg_type}' ({exc})",
				)
				continue

			subscription = self._node.create_subscription(
				msg_cls,
				topic_cfg.name,
				lambda msg, cfg=topic_cfg: self._handle_message(cfg, msg),
				topic_cfg.qos_depth,
			)
			self._subscriptions.append(subscription)

		if not self._subscriptions:
			self.event_bus.publish_sync(
				"log",
				f"ROS2 client '{self.config.name}' started with 0 valid subscriptions; stopping",
			)
			self.stop()
			return

		self._thread = Thread(target=self._spin_loop, name=self.config.name, daemon=True)
		self._thread.start()

		self.event_bus.publish_sync(
			"log",
			f"ROS2 client '{self.config.name}' started with {len(self._subscriptions)} subscriptions",
		)

	def stop(self) -> None:
		self._stop_event.set()

		if self._thread is not None:
			self._thread.join(timeout=1.0)
			self._thread = None

		self._subscriptions.clear()

		if self._executor is not None and self._node is not None:
			try:
				self._executor.remove_node(self._node)
			except Exception:
				pass

		if self._executor is not None:
			try:
				self._executor.shutdown()
			except Exception:
				pass
			self._executor = None

		if self._node is not None:
			try:
				self._node.destroy_node()
			except Exception:
				pass
			self._node = None

		if self._owns_rclpy_context and ROS2_AVAILABLE and rclpy is not None and rclpy.ok():
			try:
				rclpy.shutdown()
			except Exception:
				pass
		self._owns_rclpy_context = False

	def _spin_loop(self) -> None:
		while not self._stop_event.is_set() and self._executor is not None:
			try:
				self._executor.spin_once(timeout_sec=self.config.spin_timeout_s)
			except Exception as exc:
				self.event_bus.publish_sync(
					"log",
					f"ROS2 client '{self.config.name}' spin error: {exc}",
				)
				break

	_TRANSFORMS: dict[str, str] = {
		"dynamic_joint_states": "_transform_dynamic_joint_states",
		"joy": "_transform_joy",
	}

	def _handle_message(self, topic_cfg: ROS2TopicConfig, msg: Any) -> None:
		payload = self._message_to_payload(msg)
		if topic_cfg.transform and topic_cfg.transform in self._TRANSFORMS:
			method = getattr(self, self._TRANSFORMS[topic_cfg.transform])
			method(topic_cfg, payload)
		else:
			self.event_bus.publish_sync(self._event_topic(topic_cfg), payload)

	def _event_topic(self, topic_cfg: ROS2TopicConfig) -> str:
		if topic_cfg.event_topic:
			return topic_cfg.event_topic
		if self.config.event_prefix:
			return f"{self.config.event_prefix}.{topic_cfg.name.lstrip('/')}"
		return topic_cfg.name

	def _transform_dynamic_joint_states(self, topic_cfg: ROS2TopicConfig, payload: dict) -> None:
		prefix = self._event_topic(topic_cfg)
		joint_names = payload.get("joint_names", [])
		interface_values = payload.get("interface_values", [])

		self.event_bus.publish_sync(prefix, payload)

		for joint_name, joint_data in zip(joint_names, interface_values):
			names = joint_data.get("interface_names", [])
			values = joint_data.get("values", [])
			joint_snapshot = dict(zip(names, values))

			joint_topic = f"{prefix}.{joint_name}"
			self.event_bus.publish_sync(joint_topic, joint_snapshot)

			for field_name, value in joint_snapshot.items():
				self.event_bus.publish_sync(f"{joint_topic}.{field_name}", value)

	def _transform_joy(self, topic_cfg: ROS2TopicConfig, payload: dict) -> None:
		"""
		Transform Joy message to individual input events.
		Publishes each button and axis on separate event topics.
		
		Published topics:
		- {prefix}.button.{index}: button state (0 or 1)
		- {prefix}.axis.{index}: axis value (float, usually -1.0 to 1.0)
		"""
		prefix = self._event_topic(topic_cfg)
		
		# Publish full payload for components that need it
		self.event_bus.publish_sync(prefix, payload)
		
		# Publish each button individually
		buttons = payload.get("buttons", [])
		for button_idx, button_value in enumerate(buttons):
			button_topic = f"{prefix}.button.{button_idx}"
			self.event_bus.publish_sync(button_topic, button_value)
		
		# Publish each axis individually
		axes = payload.get("axes", [])
		for axis_idx, axis_value in enumerate(axes):
			axis_topic = f"{prefix}.axis.{axis_idx}"
			self.event_bus.publish_sync(axis_topic, axis_value)

	def _message_to_payload(self, msg: Any) -> Any:
		if message_to_ordereddict is not None:
			try:
				return message_to_ordereddict(msg)
			except Exception:
				pass

		if hasattr(msg, "__dict__"):
			return dict(msg.__dict__)
		return str(msg)

	def _parse_topics(self, topics: list[Any]) -> list[ROS2TopicConfig]:
		parsed: list[ROS2TopicConfig] = []
		for topic in topics:
			if isinstance(topic, str):
				topic_name = topic.strip()
				if not topic_name:
					continue
				parsed.append(ROS2TopicConfig(name=topic_name))
				continue

			if not isinstance(topic, dict):
				continue

			topic_name = str(topic.get("name", "")).strip()
			if not topic_name:
				continue

			parsed.append(
				ROS2TopicConfig(
					name=topic_name,
					msg_type=str(topic.get("msg_type", "std_msgs/msg/String")).strip(),
					qos_depth=max(1, int(topic.get("qos_depth", 10))),
					event_topic=str(topic.get("event_topic", "")).strip(),
					transform=str(topic.get("transform", "")).strip(),
				)
			)

		return parsed
