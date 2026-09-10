"""
Stream Forwarder Test
=====================
Self-contained test for the live stream forwarder: serialization, batching,
backpressure drop policy, and retry-on-failure. Spins up a throwaway HTTP
server as the sink; no external services required.

Usage:
    python test_stream_forwarder.py
"""

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from stream_forwarder import StreamForwarder, influx_line_protocol


def _frame(i: int) -> dict:
    return {
        "id": 0x100 + (i % 4),
        "data": [i & 0xFF, 0, 1, 2],
        "received_at": time.time(),
        "is_extended": False,
        "is_remote": False,
        "dlc": 4,
        "decoded": {"message_name": "M", "signals": {"S": {"value": float(i)}}},
    }


def test_serializer():
    lines = influx_line_protocol(
        [
            (
                {
                    "id": 0x123, "data": [1, 2], "received_at": time.time(),
                    "is_extended": False, "is_remote": False, "dlc": 2,
                    "decoded": {"message_name": "H", "signals": {
                        "State": {"value": "ACTIVE", "raw": 1},
                        "V": {"value": 48.5, "unit": "V"},
                    }},
                },
                "live",
            ),
            ({"type": "heartbeat"}, "live"),  # control message, skipped
        ],
        {"include_frames": True, "include_signals": True,
         "measurement_frame": "can_frame", "measurement_signal": "can_signal"},
    ).splitlines()

    assert any(l.startswith("can_frame,can_id=0x123,source=live") for l in lines)
    assert any('signal=State value=1.0,state="ACTIVE"' in l for l in lines)
    assert any("signal=V,unit=V value=48.5" in l for l in lines)
    assert len(lines) == 3  # 1 frame + 2 signals, no heartbeat
    print("test_serializer: OK")


def test_forward_and_retry():
    received = []
    fail_next = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if fail_next["n"] > 0:
                fail_next["n"] -= 1
                self.send_response(503)
                self.end_headers()
                return
            received.append(body.decode())
            self.send_response(204)
            self.end_headers()

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]

    async def run():
        fwd = StreamForwarder()
        fwd._config.update({
            "enabled": True,
            "url": f"http://127.0.0.1:{port}/write",
            "token": "secret",
            "batch_size": 50,
            "flush_ms": 100,
        })
        await fwd.start()

        for i in range(120):
            fwd.enqueue(_frame(i), "live")
        await asyncio.sleep(0.5)

        fail_next["n"] = 2  # force two 503s, then success
        for i in range(10):
            fwd.enqueue(_frame(i), "sim")
        await asyncio.sleep(3.5)

        status = fwd.status()
        await fwd.stop()
        srv.shutdown()

        assert status["sent"] == 130, status["sent"]
        assert status["dropped"] == 0, status["dropped"]
        assert status["failures"] == 2, status["failures"]
        total_lines = sum(len(b.strip().splitlines()) for b in received)
        assert total_lines == 260, total_lines  # 130 frames * (1 frame + 1 signal)
        print("test_forward_and_retry: OK")

    asyncio.run(run())


def test_backpressure_drop():
    async def run():
        fwd = StreamForwarder()
        fwd._config.update({"enabled": True, "url": "http://127.0.0.1:1/none"})
        # tiny queue, never started -> enqueue is a no-op until running
        fwd._queue = asyncio.Queue(maxsize=5)
        fwd._running = True
        for i in range(20):
            fwd.enqueue(_frame(i), "live")
        assert fwd._queue.qsize() == 5
        assert fwd._dropped == 15, fwd._dropped
        fwd._running = False
        print("test_backpressure_drop: OK")

    asyncio.run(run())


if __name__ == "__main__":
    test_serializer()
    test_backpressure_drop()
    test_forward_and_retry()
    print("\nAll stream forwarder tests passed.")
