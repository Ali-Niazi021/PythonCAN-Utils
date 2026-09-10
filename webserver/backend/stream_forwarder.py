"""
Stream Forwarder
================
Forwards live CAN traffic (real, simulated, and test-mode frames) to an
external time-series database so dashboards / live graphs can be built on
another server.

The API broadcast path (``CANBackend.broadcast_message``) pushes every frame
onto a bounded in-memory queue. A background asyncio task drains the queue,
batches frames, serializes them, and POSTs them to the configured sink.

A slow or unreachable sink never blocks CAN reception: when the queue is
full the oldest frames are dropped and counted.

The default serializer targets InfluxDB v2 line protocol (``/api/v2/write``),
but the serializer is pluggable via ``SERIALIZERS``.

Configuration comes from environment variables (defaults) overlaid with a
persisted ``stream_forward_config.json`` that the runtime config endpoint
writes. Environment variables:

    STREAM_FORWARD_ENABLED        true/false (default false)
    STREAM_FORWARD_URL            full write URL, e.g.
                                  http://dbhost:8086/api/v2/write?org=trev&bucket=can&precision=ns
    STREAM_FORWARD_TOKEN          auth token (sent as "Authorization: Token <token>")
    STREAM_FORWARD_SERIALIZER     influx (default)
    STREAM_FORWARD_BATCH_SIZE     max frames per POST (default 5000)
    STREAM_FORWARD_FLUSH_MS       max buffering delay before a POST (default 250)
    STREAM_FORWARD_QUEUE_MAX      max buffered frames (default 50000)
    STREAM_FORWARD_INCLUDE_FRAMES   emit raw frame points (default true)
    STREAM_FORWARD_INCLUDE_SIGNALS  emit decoded signal points (default true)
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    print("Warning: httpx not installed. Stream forwarding disabled.")


CONFIG_FILE = Path(__file__).parent / "stream_forward_config.json"

# Config keys a client may change at runtime via POST /stream/forward/config.
MUTABLE_KEYS = {
    "enabled",
    "url",
    "token",
    "serializer",
    "batch_size",
    "flush_ms",
    "include_frames",
    "include_signals",
    "measurement_frame",
    "measurement_signal",
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_config() -> Dict[str, Any]:
    return {
        "enabled": _env_bool("STREAM_FORWARD_ENABLED", False),
        "url": os.getenv("STREAM_FORWARD_URL", ""),
        "token": os.getenv("STREAM_FORWARD_TOKEN", ""),
        "serializer": os.getenv("STREAM_FORWARD_SERIALIZER", "influx"),
        "batch_size": _env_int("STREAM_FORWARD_BATCH_SIZE", 5000),
        "flush_ms": _env_int("STREAM_FORWARD_FLUSH_MS", 250),
        "queue_max": _env_int("STREAM_FORWARD_QUEUE_MAX", 50000),
        "include_frames": _env_bool("STREAM_FORWARD_INCLUDE_FRAMES", True),
        "include_signals": _env_bool("STREAM_FORWARD_INCLUDE_SIGNALS", True),
        "measurement_frame": os.getenv("STREAM_FORWARD_MEASUREMENT_FRAME", "can_frame"),
        "measurement_signal": os.getenv("STREAM_FORWARD_MEASUREMENT_SIGNAL", "can_signal"),
    }


def _load_persisted_config() -> Dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        return payload if isinstance(payload, dict) else {}
    except Exception as e:
        print(f"[Forwarder] Failed to read {CONFIG_FILE.name}: {e}")
        return {}


def _persist_config(config: Dict[str, Any]) -> None:
    payload = {key: config[key] for key in MUTABLE_KEYS if key in config}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
            json.dump(payload, config_file, indent=2)
    except Exception as e:
        print(f"[Forwarder] Failed to persist {CONFIG_FILE.name}: {e}")


# ----------------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------------

def _frame_timestamp_ns(message: Dict[str, Any]) -> int:
    """Best-effort epoch nanoseconds for a frame.

    Some adapters report an adapter-relative ``timestamp`` (seconds since the
    device booted) rather than epoch time, so prefer ``received_at`` and fall
    back to wall-clock time when a value is clearly not epoch-based.
    """
    epoch_floor = 1_000_000_000  # ~2001-09-09; anything below is not epoch time
    for key in ("received_at", "timestamp"):
        value = message.get(key)
        if isinstance(value, (int, float)) and value >= epoch_floor:
            return int(value * 1e9)
    return int(time.time() * 1e9)


def _esc_tag(value: str) -> str:
    """Escape a line-protocol tag key/value or field key."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace("=", "\\=")
        .replace(" ", "\\ ")
    )


def _esc_measurement(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _esc_str_field(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _source_of(message: Dict[str, Any], default_source: str) -> str:
    raw = message.get("source")
    if raw == "hvc_test_mode_tx":
        return "hvc_test"
    if isinstance(raw, str) and raw:
        return raw
    return default_source


def influx_line_protocol(batch: List[Tuple[Dict[str, Any], str]], config: Dict[str, Any]) -> str:
    """Serialize a batch of (message, default_source) pairs to Influx line protocol."""
    include_frames = bool(config.get("include_frames", True))
    include_signals = bool(config.get("include_signals", True))
    frame_measurement = _esc_measurement(config.get("measurement_frame") or "can_frame")
    signal_measurement = _esc_measurement(config.get("measurement_signal") or "can_signal")

    lines: List[str] = []

    for message, default_source in batch:
        if "id" not in message:
            continue

        can_id = message["id"]
        can_id_tag = f"0x{can_id:X}" if isinstance(can_id, int) else _esc_tag(str(can_id))
        source = _esc_tag(_source_of(message, default_source))
        ext = "true" if message.get("is_extended") else "false"
        ts_ns = _frame_timestamp_ns(message)

        if include_frames:
            data_bytes = message.get("data") or []
            fields = [f"dlc={int(message.get('dlc', len(data_bytes)))}i"]
            if data_bytes:
                data_hex = "".join(f"{int(b) & 0xFF:02X}" for b in data_bytes)
                fields.append(f'data="{data_hex}"')
                for index, byte_value in enumerate(data_bytes):
                    fields.append(f"b{index}={int(byte_value) & 0xFF}i")
            fields.append("remote=" + ("true" if message.get("is_remote") else "false"))
            lines.append(
                f"{frame_measurement},can_id={can_id_tag},source={source},ext={ext} "
                f"{','.join(fields)} {ts_ns}"
            )

        if not include_signals:
            continue

        decoded = message.get("decoded")
        if not isinstance(decoded, dict):
            continue

        message_name = _esc_tag(decoded.get("message_name") or "unknown")
        signals = decoded.get("signals")
        if not isinstance(signals, dict):
            continue

        for signal_name, signal_info in signals.items():
            if isinstance(signal_info, dict):
                value = signal_info.get("value")
                raw = signal_info.get("raw")
                unit = signal_info.get("unit")
            else:
                value = signal_info
                raw = None
                unit = None

            numeric: Optional[float] = None
            state: Optional[str] = None
            if isinstance(value, bool):
                numeric = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                numeric = float(value)
            elif isinstance(value, str):
                state = value
                if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    numeric = float(raw)

            if numeric is None and state is None:
                continue

            tags = (
                f",can_id={can_id_tag},source={source},message={message_name}"
                f",signal={_esc_tag(signal_name)}"
            )
            if unit:
                tags += f",unit={_esc_tag(unit)}"

            field_parts: List[str] = []
            if numeric is not None:
                field_parts.append(f"value={numeric}")
            if state is not None:
                field_parts.append(f'state="{_esc_str_field(state)}"')

            lines.append(f"{signal_measurement}{tags} {','.join(field_parts)} {ts_ns}")

    return "\n".join(lines)


SERIALIZERS = {
    "influx": influx_line_protocol,
}


# ----------------------------------------------------------------------------
# Forwarder
# ----------------------------------------------------------------------------

class StreamForwarder:
    """Batches live CAN frames and ships them to an external time-series DB."""

    def __init__(self) -> None:
        self._config: Dict[str, Any] = {**_default_config(), **_load_persisted_config()}
        queue_max = max(1000, int(self._config.get("queue_max", 50000)))
        self._queue: "asyncio.Queue[Tuple[Dict[str, Any], str]]" = asyncio.Queue(maxsize=queue_max)
        self._task: Optional[asyncio.Task] = None
        self._client: Optional["httpx.AsyncClient"] = None
        self._running = False
        self._started_at: Optional[float] = None

        # statistics
        self._enqueued = 0
        self._dropped = 0
        self._sent = 0
        self._batches = 0
        self._failures = 0
        self._last_error: Optional[str] = None
        self._last_success_ts: Optional[float] = None

    # -- production side (called from the event loop by broadcast_message) --

    def enqueue(self, message: Dict[str, Any], source: str = "live") -> None:
        """Non-blocking hand-off of one frame. Drops oldest on backpressure."""
        if not self._running or not self._config.get("enabled"):
            return
        if message.get("type") or "id" not in message:
            return  # control messages (connection_status / heartbeat)

        item = (message, source)
        try:
            self._queue.put_nowait(item)
            self._enqueued += 1
            return
        except asyncio.QueueFull:
            pass

        try:
            self._queue.get_nowait()
            self._dropped += 1
            self._queue.put_nowait(item)
            self._enqueued += 1
        except (asyncio.QueueEmpty, asyncio.QueueFull):
            self._dropped += 1

    # -- lifecycle --

    async def start(self) -> None:
        if self._running:
            return
        if not HTTPX_AVAILABLE:
            self._last_error = "httpx not installed"
            return
        self._running = True
        self._started_at = time.time()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        self._task = asyncio.create_task(self._run())
        print(
            f"[Forwarder] Started (enabled={self._config.get('enabled')}, "
            f"url={self._config.get('url') or '<unset>'})"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def apply_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge runtime config changes, persist them, and restart the drain loop."""
        for key, value in updates.items():
            if key in MUTABLE_KEYS and value is not None:
                self._config[key] = value

        _persist_config(self._config)

        was_running = self._running
        if was_running:
            await self.stop()
        if self._config.get("enabled") or was_running:
            await self.start()
        return self.status()

    # -- consumption side --

    async def _run(self) -> None:
        flush_s = max(0.02, int(self._config.get("flush_ms", 250)) / 1000.0)
        batch_size = max(1, int(self._config.get("batch_size", 5000)))

        while self._running:
            try:
                first = await self._queue.get()
            except asyncio.CancelledError:
                break

            batch: List[Tuple[Dict[str, Any], str]] = [first]
            deadline = time.monotonic() + flush_s
            while len(batch) < batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self._queue.get(), remaining))
                except asyncio.TimeoutError:
                    break
                except asyncio.CancelledError:
                    self._running = False
                    break

            try:
                await self._flush(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:  # never let the drain loop die
                self._failures += 1
                self._last_error = f"{type(e).__name__}: {e}"

    async def _flush(self, batch: List[Tuple[Dict[str, Any], str]]) -> None:
        if not batch or not self._client:
            return
        if not self._config.get("enabled") or not self._config.get("url"):
            self._dropped += len(batch)
            return

        serializer = SERIALIZERS.get(self._config.get("serializer", "influx"))
        if serializer is None:
            self._last_error = f"unknown serializer '{self._config.get('serializer')}'"
            self._dropped += len(batch)
            return

        payload = serializer(batch, self._config)
        if not payload:
            return

        headers = {"Content-Type": "text/plain; charset=utf-8"}
        token = self._config.get("token")
        if token:
            headers["Authorization"] = f"Token {token}"

        backoff = 0.5
        for attempt in range(3):
            try:
                response = await self._client.post(
                    self._config["url"], content=payload, headers=headers
                )
                if response.status_code < 300:
                    self._sent += len(batch)
                    self._batches += 1
                    self._last_success_ts = time.time()
                    return
                self._last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"

            self._failures += 1
            if attempt < 2:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 3, 5.0)

        self._dropped += len(batch)  # give up on this batch

    # -- introspection --

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self._config.get("enabled")),
            "running": self._running,
            "httpx_available": HTTPX_AVAILABLE,
            "url": self._config.get("url", ""),
            "has_token": bool(self._config.get("token")),
            "serializer": self._config.get("serializer", "influx"),
            "batch_size": int(self._config.get("batch_size", 5000)),
            "flush_ms": int(self._config.get("flush_ms", 250)),
            "include_frames": bool(self._config.get("include_frames", True)),
            "include_signals": bool(self._config.get("include_signals", True)),
            "queue_size": self._queue.qsize(),
            "queue_max": self._queue.maxsize,
            "enqueued": self._enqueued,
            "sent": self._sent,
            "dropped": self._dropped,
            "batches": self._batches,
            "failures": self._failures,
            "last_error": self._last_error,
            "last_success_ts": self._last_success_ts,
            "uptime_seconds": (time.time() - self._started_at) if self._started_at else 0,
        }
