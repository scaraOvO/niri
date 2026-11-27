from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import subprocess
import time

import appearance


def recent(paths):
    entries = []
    for path in paths:
        try:
            entries.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    return [path for _, path in sorted(entries, reverse=True)[:8]]


def decoded(lines):
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                yield value
        except (UnicodeError, ValueError):
            continue


def logs(path):
    try:
        if path.suffix != ".zstd":
            with path.open("rb") as stream:
                yield from decoded(stream)
            return
        # 正在写入的最后一个压缩帧可能不完整，前面的完整记录仍可用。
        with subprocess.Popen(["zstd", "-dc", "--", str(path)], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as process:
            yield from decoded(process.stdout)
    except OSError:
        return


def count(raw, key):
    value = raw.get(key)
    return value if type(value) is int and value >= 0 else 0


def result(rows, stamp):
    totals = {}
    for row in rows:
        for key, value in row.items():
            totals[key] = totals.get(key, 0) + value
    if totals:
        totals["total_tokens"] = sum(totals.values())
        return totals, stamp
    return None


def codex():
    root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    for path in recent((root / "sessions").glob("*/*/*/*.jsonl")):
        try:
            with path.open("rb") as stream:
                stream.seek(max(0, path.stat().st_size - 2 * 1024 * 1024))
                entries = list(decoded(stream))
        except OSError:
            continue
        for event in reversed(entries):
            payload = event.get("payload") or {}
            if event.get("type") != "event_msg" or not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            info = payload.get("info") or {}
            usage = info.get("total_token_usage") if isinstance(info, dict) else None
            if isinstance(usage, dict) and type(usage.get("total_tokens")) is int:
                return usage, event.get("timestamp", "")
    return None


def claude():
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    for path in recent((root / "projects").glob("*/*.jsonl")):
        rows, stamp = {}, ""
        for index, event in enumerate(logs(path)):
            if event.get("type") != "assistant":
                continue
            message = event.get("message") or {}
            raw = message.get("usage") if isinstance(message, dict) else None
            keys = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
            if not isinstance(raw, dict) or not any(type(raw.get(key)) is int for key in keys):
                continue
            row = dict(zip(("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"),
                           (count(raw, key) for key in keys)))
            identity = message.get("id") or event.get("uuid") or index
            rows[identity] = row
            stamp = event.get("timestamp") or stamp
        usage = result(rows.values(), stamp)
        if usage:
            return usage
    return None


def harness_files():
    roots = os.environ.get("DSH_HOME", str(Path.home() / ".dsh")).split(",")
    generations = {}
    for root in roots:
        if not root.strip():
            continue
        for path in (Path(root.strip()).expanduser() / "sessions").glob("*/*/session*.jsonl*"):
            match = re.fullmatch(r"session(?:\.v([0-9]+))?\.jsonl(\.zstd)?", path.name)
            if not match:
                continue
            version = int(match[1] or 0)
            try:
                key = (version, path.stat().st_mtime_ns)
            except OSError:
                continue
            current = generations.get(path.parent)
            if current is None or key > current[0]:
                generations[path.parent] = (key, path)
    return (path for _, path in generations.values())


def harness_counts(raw):
    keys = ("inputTokens", "cacheReadTokens", "cacheWriteTokens", "outputTokens")
    if not isinstance(raw, dict) or not any(type(raw.get(key)) is int for key in keys):
        return None
    return dict(zip(("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens"),
                    (count(raw, key) for key in keys)))


def harness():
    for path in recent(harness_files()):
        rows, retries, settled, stamp = {}, {}, set(), ""
        for index, record in enumerate(logs(path)):
            event = record.get("event", record)
            if not isinstance(event, dict):
                continue
            name = event.get("type")
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            turn, step = data.get("turn"), data.get("step")
            position = (turn, step) if type(turn) is int and type(step) is int else (index, None)
            if name == "llm/retry-started":
                retries[position] = retries.get(position, 0) + 1
                continue
            key = (*position, retries.get(position, 0))
            if name not in ("assistant/message", "assistant/attempt", "assistant/chunk"):
                continue
            if name != "assistant/message" and key in settled:
                continue
            usage = harness_counts(data.get("usage"))
            if usage is None and isinstance(data.get("stream"), list):
                for entry in reversed(data["stream"]):
                    if isinstance(entry, dict):
                        chunk = entry.get("chunk", entry)
                        if isinstance(chunk, dict) and chunk.get("type") == "usage":
                            usage = harness_counts(chunk.get("usage"))
                            if usage is not None:
                                break
            chunk = data.get("chunk")
            if usage is None and isinstance(chunk, dict) and chunk.get("type") == "usage":
                usage = harness_counts(chunk.get("usage"))
            if usage is not None:
                rows[key] = usage
                if name == "assistant/message":
                    settled.add(key)
                updated = event.get("timestamp") or event.get("ts") or event.get("time")
                if isinstance(updated, str):
                    stamp = updated
                elif type(updated) in (int, float) and updated > 1_000_000_000:
                    try:
                        seconds = updated / 1000 if updated > 10_000_000_000 else updated
                        stamp = datetime.fromtimestamp(seconds, timezone.utc).isoformat()
                    except (ValueError, OverflowError, OSError):
                        pass
        usage = result(rows.values(), stamp)
        if usage:
            return usage
    return None


def available_usage():
    # Waybar 每秒刷新，短缓存避免反复扫描同一份会话。
    cache = appearance.STATE / "island-usage.json"
    key = [os.environ.get(name) for name in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "DSH_HOME")]
    try:
        if time.time() - cache.stat().st_mtime < 8:
            cached = json.loads(cache.read_text())
            if cached["roots"] == key and isinstance(cached["sources"], list):
                return cached["sources"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    sources = []
    for name, short, reader in (("Codex", "CX", codex), ("Claude Code", "CC", claude), ("DeepSeek Harness", "DS", harness)):
        reading = reader()
        if reading is not None:
            usage, updated = reading
            sources.append([name, short, usage, updated if isinstance(updated, str) else ""])
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        pending = cache.with_name(f"{cache.name}.{os.getpid()}.tmp")
        pending.write_text(json.dumps({"roots": key, "sources": sources}))
        pending.replace(cache)
    except OSError:
        pass
    return sources
