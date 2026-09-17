from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


def _canonical_json(value: Mapping[str, JSONValue]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_fingerprint(value: Mapping[str, JSONValue]) -> str:
    """Return a stable SHA-256 fingerprint for JSON-compatible configuration."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _distribution_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not-installed"


def software_identity() -> dict[str, JSONValue]:
    """Fingerprint the executing AMEP package and behavior-critical dependencies.

    The package-tree digest is computed from every ``.py`` file in the installed
    ``amep1`` package. This binds replay evidence to actual source bytes even when
    a Git commit identifier is unavailable in the runtime environment.
    """
    package_root = Path(__file__).resolve().parent
    file_hashes: dict[str, JSONValue] = {}
    for path in sorted(package_root.rglob("*.py")):
        relative = path.relative_to(package_root).as_posix()
        file_hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    package_tree_sha256 = canonical_fingerprint({"files": file_hashes})
    return {
        "package_tree_sha256": package_tree_sha256,
        "python": sys.version.split()[0],
        "distributions": {
            "amep1": _distribution_version("amep1"),
            "numpy": _distribution_version("numpy"),
            "scipy": _distribution_version("scipy"),
        },
    }


@dataclass(frozen=True)
class EvidenceRecord:
    sequence: int
    event_type: str
    timestamp_s: float | None
    payload: Mapping[str, JSONValue]
    previous_hash: str
    record_hash: str

    def body(self) -> dict[str, JSONValue]:
        return {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp_s": self.timestamp_s,
            "payload": dict(self.payload),
            "previous_hash": self.previous_hash,
        }


@dataclass(frozen=True)
class EvidenceVerification:
    valid: bool
    records_checked: int
    first_invalid_sequence: int | None = None
    reason: str = "ok"


class EvidenceLog:
    """Canonical SHA-256 hash chain for replay and assurance artifacts.

    This supplies deterministic tamper-evidence for software experiments. It is
    not a digital signature, secure clock, trusted logger, or classified audit
    mechanism.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    @staticmethod
    def _hash_body(body: Mapping[str, JSONValue]) -> str:
        return canonical_fingerprint(body)

    def append(
        self,
        event_type: str,
        *,
        timestamp_s: float | None,
        payload: Mapping[str, JSONValue],
    ) -> EvidenceRecord:
        if not event_type:
            raise ValueError("event_type must be non-empty")
        previous = self._records[-1].record_hash if self._records else self.GENESIS_HASH
        body: dict[str, JSONValue] = {
            "sequence": len(self._records),
            "event_type": event_type,
            "timestamp_s": timestamp_s,
            "payload": dict(payload),
            "previous_hash": previous,
        }
        record = EvidenceRecord(
            sequence=len(self._records),
            event_type=event_type,
            timestamp_s=timestamp_s,
            payload=dict(payload),
            previous_hash=previous,
            record_hash=self._hash_body(body),
        )
        self._records.append(record)
        return record

    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def to_jsonl(self) -> str:
        lines = []
        for record in self._records:
            value = record.body()
            value["record_hash"] = record.record_hash
            lines.append(_canonical_json(value))
        return "\n".join(lines) + ("\n" if lines else "")

    @classmethod
    def verify(cls, records: Iterable[EvidenceRecord]) -> EvidenceVerification:
        previous = cls.GENESIS_HASH
        count = 0
        for expected_sequence, record in enumerate(records):
            count += 1
            if record.sequence != expected_sequence:
                return EvidenceVerification(
                    False, count, record.sequence, "sequence_mismatch"
                )
            if record.previous_hash != previous:
                return EvidenceVerification(
                    False, count, record.sequence, "previous_hash_mismatch"
                )
            expected_hash = cls._hash_body(record.body())
            if record.record_hash != expected_hash:
                return EvidenceVerification(
                    False, count, record.sequence, "record_hash_mismatch"
                )
            previous = record.record_hash
        return EvidenceVerification(True, count)

    @classmethod
    def from_jsonl(cls, text: str) -> EvidenceLog:
        log = cls()
        records: list[EvidenceRecord] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            value: dict[str, Any] = json.loads(line)
            records.append(
                EvidenceRecord(
                    sequence=int(value["sequence"]),
                    event_type=str(value["event_type"]),
                    timestamp_s=(
                        None
                        if value["timestamp_s"] is None
                        else float(value["timestamp_s"])
                    ),
                    payload=dict(value["payload"]),
                    previous_hash=str(value["previous_hash"]),
                    record_hash=str(value["record_hash"]),
                )
            )
        verification = cls.verify(records)
        if not verification.valid:
            raise ValueError(f"invalid evidence log: {verification.reason}")
        log._records.extend(records)
        return log
