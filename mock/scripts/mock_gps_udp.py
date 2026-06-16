"""
Mock GPS UDP broadcaster.

Sends GPS coordinates (JSON) on port 7010 as a UDP broadcast, simulating
movement around a fixed origin. No external dependencies required.

Usage:
    python mock/scripts/mock_gps_udp.py [--interval 0.5] [--radius 50]
"""

import argparse
import json
import math
import socket
import time

# ── WGS84 constants ────────────────────────────────────────────────────────────
_A  = 6_378_137.0
_F  = 1 / 298.257_223_563
_B  = _A * (1 - _F)
_E2 = 2 * _F - _F ** 2
_K0 = 0.9996


def _lat_lon_to_utm(lat_deg: float, lon_deg: float) -> tuple[str, float, float]:
    """Return (zone_str, easting, northing) for a WGS84 lat/lon."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    zone_num = int((lon_deg + 180) / 6) + 1
    lon0 = math.radians((zone_num - 1) * 6 - 180 + 3)

    n  = _A / math.sqrt(1 - _E2 * math.sin(lat) ** 2)
    t  = math.tan(lat) ** 2
    c  = _E2 / (1 - _E2) * math.cos(lat) ** 2
    a_ = math.cos(lat) * (lon - lon0)

    e2 = _E2
    m = _A * (
        (1 - e2/4 - 3*e2**2/64 - 5*e2**3/256) * lat
        - (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024) * math.sin(2*lat)
        + (15*e2**2/256 + 45*e2**3/1024) * math.sin(4*lat)
        - (35*e2**3/3072) * math.sin(6*lat)
    )

    easting = _K0 * n * (
        a_
        + a_**3/6  * (1 - t + c)
        + a_**5/120 * (5 - 18*t + t**2 + 72*c - 58*(_E2/(1-_E2)))
    ) + 500_000.0

    northing = _K0 * (
        m + n * math.tan(lat) * (
            a_**2/2
            + a_**4/24 * (5 - t + 9*c + 4*c**2)
            + a_**6/720 * (61 - 58*t + t**2 + 600*c - 330*(_E2/(1-_E2)))
        )
    )
    if lat_deg < 0:
        northing += 10_000_000.0

    band = "CDEFGHJKLMNPQRSTUVWXX"[int((lat_deg + 80) / 8)]
    return f"{zone_num}{band}", easting, northing


def _make_packet(lat: float, lon: float, alt: float, speed: float, track: float) -> bytes:
    ts = time.time()
    zone, easting, northing = _lat_lon_to_utm(lat, lon)
    payload = {
        "timestamp":  round(ts, 6),
        "utm_zone":   zone,
        "easting":    round(easting, 2),
        "northing":   round(northing, 2),
        "lat":        round(lat, 6),
        "lon":        round(lon, 6),
        "alt_msl":    round(alt, 2),
        "speed_ms":   round(speed, 3),
        "track_deg":  round(track % 360, 2),
        "accuracy_m": 4.89,
        "elrob":      f"{ts:.6f} {zone} {easting:.2f} {northing:.2f}",
    }
    return json.dumps(payload).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock GPS UDP broadcaster on port 7010")
    parser.add_argument("--lat",      type=float, default=46.759,  help="Origin latitude")
    parser.add_argument("--lon",      type=float, default=7.616,   help="Origin longitude")
    parser.add_argument("--alt",      type=float, default=650.0,   help="Altitude MSL (m)")
    parser.add_argument("--radius",   type=float, default=30.0,    help="Circle radius (m)")
    parser.add_argument("--speed",    type=float, default=0.8,     help="Speed (m/s)")
    parser.add_argument("--interval", type=float, default=0.5,     help="Broadcast interval (s)")
    parser.add_argument("--port",     type=int,   default=7010,    help="UDP port")
    parser.add_argument("--host",     type=str,   default="<broadcast>", help="Broadcast address")
    args = parser.parse_args()

    # metres per degree at the origin
    m_per_lat = 111_320.0
    m_per_lon = 111_320.0 * math.cos(math.radians(args.lat))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    angle = 0.0
    # angular speed so the robot covers the circle at the requested speed
    omega = args.speed / max(args.radius, 0.1)  # rad/s

    print(f"Broadcasting GPS on {args.host}:{args.port} every {args.interval}s")
    print(f"Origin: {args.lat}, {args.lon}  radius={args.radius}m  speed={args.speed}m/s")
    print("Ctrl-C to stop.\n")

    try:
        while True:
            lat = args.lat + (args.radius * math.sin(angle)) / m_per_lat
            lon = args.lon + (args.radius * math.cos(angle)) / m_per_lon
            track = math.degrees(angle + math.pi / 2) % 360  # tangent direction

            pkt = _make_packet(lat, lon, args.alt, args.speed, track)
            sock.sendto(pkt, (args.host, args.port))
            print(pkt.decode(), flush=True)

            angle += omega * args.interval
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
