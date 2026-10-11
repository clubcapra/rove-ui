"""One robot address for every service and window in the operator UI."""
from __future__ import annotations

import json
import os
import socket
from functools import lru_cache
from urllib.request import ProxyHandler, build_opener

ROBOT_HOSTS = ("192.168.2.2", "192.168.1.2")
TOKEN = "${ROBOT_HOST}"


def _direct_route(host: str) -> bool:
    # The two operator networks are /24. Inspect the route's source address;
    # UDP connect sends no packet. This favors the Deck's current subnet when
    # the other address is also reachable through a router.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((host, 8080))
            source = probe.getsockname()[0]
        return source.rsplit(".", 1)[0] == host.rsplit(".", 1)[0]
    except OSError:
        return False


@lru_cache(maxsize=1)
def robot_host() -> str:
    override = os.environ.get("ROVE_ROBOT_HOST", "auto").strip()
    if override and override != "auto":
        return override
    opener = build_opener(ProxyHandler({}))
    reachable = []
    for host in ROBOT_HOSTS:
        try:
            with opener.open(f"http://{host}:8080/discover", timeout=1.0) as response:
                payload = json.load(response)
            if isinstance(payload, dict) and isinstance(payload.get("sensors"), list):
                reachable.append(host)
        except (OSError, ValueError):
            continue
    if len(reachable) == 1:
        return reachable[0]
    if reachable:
        direct = [host for host in reachable if _direct_route(host)]
        if len(direct) == 1:
            return direct[0]
        raise ValueError("Both robot addresses respond. Set ROVE_ROBOT_HOST to the intended robot IP.")
    raise ValueError(
        "HALo is unreachable on atelier (192.168.2.2) and hotspot (192.168.1.2). "
        "Connect to the robot network or set ROVE_ROBOT_HOST explicitly."
    )


def resolve_config(value, host: str | None = None):
    """Expand robot placeholders; camera/radio/mapping addresses remain distinct."""
    if isinstance(value, dict):
        return {key: resolve_config(item, host) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_config(item, host) for item in value]
    if isinstance(value, str) and TOKEN in value:
        return value.replace(TOKEN, host or robot_host())
    return value
