"""Content-addressed, immutable raw input archive."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


class ImmutableRawArchive:
    def __init__(self, root="data/raw"):
        self.root = Path(root)

    def _payload(self, data):
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode("utf-8")
        return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    def write(self, provider, dataset, data, captured_at=None, extension="json"):
        payload = self._payload(data)
        digest = hashlib.sha256(payload).hexdigest()
        captured_at = captured_at or datetime.now(UTC)
        ts = captured_at.strftime("%Y%m%dT%H%M%SZ")
        directory = (
            self.root
            / str(provider)
            / str(dataset)
            / captured_at.strftime("%Y")
            / captured_at.strftime("%m")
        )
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{ts}_{digest[:16]}.{extension.lstrip('.')}"
        if path.exists():
            if path.read_bytes() != payload:
                raise ValueError("raw archive path collision with different content")
        else:
            path.write_bytes(payload)
        return str(path)

    archive = write

    write_raw = write


RawArchive = ImmutableRawArchive
