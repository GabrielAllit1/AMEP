from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import cos, isfinite, radians, sin

from .time_alignment import MeasurementEnvelope

KNOT_TO_MPS = 0.5144444444444445


def _checksum(payload: str) -> int:
    value = 0
    for char in payload:
        value ^= ord(char)
    return value


def validate_sentence(sentence: str) -> str:
    text = sentence.strip()
    if not text.startswith("$") or "*" not in text:
        raise ValueError("NMEA 0183 sentence must begin with '$' and contain checksum")
    payload, checksum_text = text[1:].rsplit("*", 1)
    if len(checksum_text) != 2:
        raise ValueError("NMEA 0183 checksum must contain two hex digits")
    try:
        expected = int(checksum_text, 16)
    except ValueError as exc:
        raise ValueError("invalid NMEA 0183 checksum encoding") from exc
    if _checksum(payload) != expected:
        raise ValueError("NMEA 0183 checksum mismatch")
    return payload


def _lat_lon(value: str, hemisphere: str, *, latitude: bool) -> float:
    if not value or hemisphere not in {"N", "S", "E", "W"}:
        raise ValueError("invalid NMEA latitude/longitude field")
    degree_digits = 2 if latitude else 3
    if len(value) <= degree_digits:
        raise ValueError("invalid NMEA latitude/longitude magnitude")
    degrees = float(value[:degree_digits])
    minutes = float(value[degree_digits:])
    if not 0.0 <= minutes < 60.0:
        raise ValueError("NMEA latitude/longitude minutes out of range")
    result = degrees + minutes / 60.0
    if hemisphere in {"S", "W"}:
        result = -result
    limit = 90.0 if latitude else 180.0
    if not -limit <= result <= limit:
        raise ValueError("NMEA latitude/longitude out of range")
    return result


@dataclass(frozen=True)
class ParsedNMEA0183:
    sentence_type: str
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    fix_quality: int | None = None
    satellites: int | None = None
    hdop: float | None = None
    altitude_m: float | None = None
    status: str | None = None
    speed_mps: float | None = None
    course_deg_true: float | None = None
    heading_deg_true: float | None = None


def parse_sentence(sentence: str) -> ParsedNMEA0183:
    payload = validate_sentence(sentence)
    fields = payload.split(",")
    if not fields or len(fields[0]) < 3:
        raise ValueError("invalid NMEA 0183 talker/sentence identifier")
    sentence_type = fields[0][-3:]
    if sentence_type == "GGA":
        if len(fields) < 10:
            raise ValueError("truncated GGA sentence")
        return ParsedNMEA0183(
            sentence_type="GGA",
            latitude_deg=_lat_lon(fields[2], fields[3], latitude=True),
            longitude_deg=_lat_lon(fields[4], fields[5], latitude=False),
            fix_quality=int(fields[6] or 0),
            satellites=int(fields[7] or 0),
            hdop=float(fields[8]) if fields[8] else None,
            altitude_m=float(fields[9]) if fields[9] else None,
        )
    if sentence_type == "RMC":
        if len(fields) < 9:
            raise ValueError("truncated RMC sentence")
        return ParsedNMEA0183(
            sentence_type="RMC",
            status=fields[2],
            latitude_deg=_lat_lon(fields[3], fields[4], latitude=True),
            longitude_deg=_lat_lon(fields[5], fields[6], latitude=False),
            speed_mps=float(fields[7] or 0.0) * KNOT_TO_MPS,
            course_deg_true=float(fields[8] or 0.0),
        )
    if sentence_type == "HDT":
        if len(fields) < 3 or fields[2] != "T":
            raise ValueError("HDT must contain true heading")
        return ParsedNMEA0183(sentence_type="HDT", heading_deg_true=float(fields[1]))
    if sentence_type == "VHW":
        if len(fields) < 6:
            raise ValueError("truncated VHW sentence")
        true_heading = float(fields[1]) if fields[1] and fields[2] == "T" else None
        speed_knots = float(fields[5]) if fields[5] else None
        return ParsedNMEA0183(
            sentence_type="VHW",
            heading_deg_true=true_heading,
            speed_mps=None if speed_knots is None else speed_knots * KNOT_TO_MPS,
        )
    raise ValueError(f"unsupported NMEA 0183 sentence type: {sentence_type}")


@dataclass(frozen=True)
class NMEA0183AdapterConfig:
    position_sigma_m: float = 3.0
    ground_velocity_sigma_mps: float = 0.25
    water_velocity_sigma_mps: float = 0.20
    heading_sigma_rad: float = radians(1.0)
    clock_domain: str = "navigation"
    provenance: str = "nmea0183.adapter"

    def __post_init__(self) -> None:
        values = (
            self.position_sigma_m,
            self.ground_velocity_sigma_mps,
            self.water_velocity_sigma_mps,
            self.heading_sigma_rad,
        )
        if not all(isfinite(float(value)) and value > 0.0 for value in values):
            raise ValueError("NMEA adapter sigmas must be finite and > 0")
        if not self.clock_domain or not self.provenance:
            raise ValueError("clock_domain and provenance must be non-empty")


class NMEA0183Adapter:
    """Checksum-validating NMEA 0183 normalization into AMEP envelopes.

    The adapter accepts actual NMEA text lines. It deliberately does not open a
    serial port or claim IEC 61162 electrical/conformance validation. GGA position
    requires a caller-supplied WGS84-to-local projector so datum/origin ownership
    remains explicit.
    """

    def __init__(
        self,
        *,
        config: NMEA0183AdapterConfig | None = None,
        geodetic_to_local: Callable[[float, float], tuple[float, float]] | None = None,
    ) -> None:
        self.config = config or NMEA0183AdapterConfig()
        self.geodetic_to_local = geodetic_to_local

    @staticmethod
    def _covariance(sigma: float, dimension: int) -> tuple[tuple[float, ...], ...]:
        variance = float(sigma) ** 2
        return tuple(
            tuple(variance if row == column else 0.0 for column in range(dimension))
            for row in range(dimension)
        )

    def _envelope(
        self,
        *,
        source: str,
        kind: str,
        values: tuple[float, ...],
        covariance: tuple[tuple[float, ...], ...],
        sentence_type: str,
        source_timestamp_s: float,
        receive_timestamp_s: float,
        timestamp_uncertainty_s: float,
        sequence: int | None,
    ) -> MeasurementEnvelope:
        return MeasurementEnvelope(
            source=source,
            kind=kind,
            source_timestamp_s=float(source_timestamp_s),
            receive_timestamp_s=float(receive_timestamp_s),
            values=values,
            covariance=covariance,
            frame="local_ENU",
            clock_domain=self.config.clock_domain,
            sequence=sequence,
            provenance=self.config.provenance,
            timestamp_uncertainty_s=float(timestamp_uncertainty_s),
            metadata={"nmea_sentence_type": sentence_type},
        )

    def adapt_line(
        self,
        sentence: str,
        *,
        source_timestamp_s: float,
        receive_timestamp_s: float,
        timestamp_uncertainty_s: float = 0.0,
        sequence: int | None = None,
    ) -> tuple[MeasurementEnvelope, ...]:
        if not all(
            isfinite(float(value))
            for value in (source_timestamp_s, receive_timestamp_s, timestamp_uncertainty_s)
        ):
            raise ValueError("NMEA adapter timestamps must be finite")
        if timestamp_uncertainty_s < 0.0:
            raise ValueError("timestamp_uncertainty_s must be >= 0")
        parsed = parse_sentence(sentence)

        if parsed.sentence_type == "GGA":
            if parsed.fix_quality is None or parsed.fix_quality <= 0:
                return ()
            if (
                self.geodetic_to_local is None
                or parsed.latitude_deg is None
                or parsed.longitude_deg is None
            ):
                return ()
            east, north = self.geodetic_to_local(parsed.latitude_deg, parsed.longitude_deg)
            return (
                self._envelope(
                    source="gnss",
                    kind="position",
                    values=(float(east), float(north)),
                    covariance=self._covariance(self.config.position_sigma_m, 2),
                    sentence_type=parsed.sentence_type,
                    source_timestamp_s=source_timestamp_s,
                    receive_timestamp_s=receive_timestamp_s,
                    timestamp_uncertainty_s=timestamp_uncertainty_s,
                    sequence=sequence,
                ),
            )

        if parsed.sentence_type == "RMC":
            if (
                parsed.status != "A"
                or parsed.course_deg_true is None
                or parsed.speed_mps is None
            ):
                return ()
            course = radians(parsed.course_deg_true)
            east = parsed.speed_mps * sin(course)
            north = parsed.speed_mps * cos(course)
            return (
                self._envelope(
                    source="ground_velocity",
                    kind="ground_velocity",
                    values=(east, north),
                    covariance=self._covariance(self.config.ground_velocity_sigma_mps, 2),
                    sentence_type=parsed.sentence_type,
                    source_timestamp_s=source_timestamp_s,
                    receive_timestamp_s=receive_timestamp_s,
                    timestamp_uncertainty_s=timestamp_uncertainty_s,
                    sequence=sequence,
                ),
            )

        if parsed.sentence_type == "HDT":
            if parsed.heading_deg_true is None:
                return ()
            return (
                self._envelope(
                    source="gyrocompass",
                    kind="heading",
                    values=(radians(parsed.heading_deg_true),),
                    covariance=self._covariance(self.config.heading_sigma_rad, 1),
                    sentence_type=parsed.sentence_type,
                    source_timestamp_s=source_timestamp_s,
                    receive_timestamp_s=receive_timestamp_s,
                    timestamp_uncertainty_s=timestamp_uncertainty_s,
                    sequence=sequence,
                ),
            )

        if parsed.sentence_type == "VHW":
            if parsed.heading_deg_true is None or parsed.speed_mps is None:
                return ()
            heading = radians(parsed.heading_deg_true)
            east = parsed.speed_mps * sin(heading)
            north = parsed.speed_mps * cos(heading)
            return (
                self._envelope(
                    source="speed_log",
                    kind="water_velocity",
                    values=(east, north),
                    covariance=self._covariance(self.config.water_velocity_sigma_mps, 2),
                    sentence_type=parsed.sentence_type,
                    source_timestamp_s=source_timestamp_s,
                    receive_timestamp_s=receive_timestamp_s,
                    timestamp_uncertainty_s=timestamp_uncertainty_s,
                    sequence=sequence,
                ),
            )

        return ()


class NMEA0183StreamDecoder:
    """Bounded CR/LF stream framer for serial/TCP byte chunks."""

    def __init__(self, *, max_sentence_bytes: int = 256) -> None:
        if max_sentence_bytes < 16:
            raise ValueError("max_sentence_bytes must be >= 16")
        self.max_sentence_bytes = int(max_sentence_bytes)
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> tuple[str, ...]:
        if not isinstance(chunk, bytes):
            raise TypeError("NMEA stream decoder expects bytes")
        self._buffer.extend(chunk)
        if len(self._buffer) > self.max_sentence_bytes * 4:
            raise ValueError("NMEA stream buffer exceeded bounded capacity")
        sentences: list[str] = []
        while b"\n" in self._buffer:
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            raw = raw.rstrip(b"\r")
            if not raw:
                continue
            if len(raw) > self.max_sentence_bytes:
                raise ValueError("NMEA sentence exceeds configured maximum length")
            try:
                sentences.append(raw.decode("ascii"))
            except UnicodeDecodeError as exc:
                raise ValueError("NMEA sentence is not ASCII") from exc
        return tuple(sentences)
