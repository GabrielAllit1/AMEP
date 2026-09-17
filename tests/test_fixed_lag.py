import numpy as np
import pytest

from amep1 import AMEPFilter, HorizontalIMUInput
from amep1.backend import DelayedMeasurementBackend, EstimatorBackend
from amep1.fixed_lag import (
    DelayedMeasurement,
    FixedLagBackendAdapter,
    FixedLagWindowError,
)


def imu(t):
    return HorizontalIMUInput(t, 0.0, 0.0, 0.0)


def test_fixed_lag_adapter_satisfies_backend_protocols():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=1.0)
    assert isinstance(backend, EstimatorBackend)
    assert isinstance(backend, DelayedMeasurementBackend)


def test_delayed_measurement_rewinds_and_replays_state():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=1.0)
    backend.predict(imu(0.0))
    backend.predict(imu(0.1))
    backend.predict(imu(0.2))

    before = backend.snapshot().east_m
    backend.ingest_delayed(
        source="gnss",
        timestamp_s=0.1,
        payload=DelayedMeasurement(
            kind="position",
            values=(0.5, 0.0),
            covariance=((0.01, 0.0), (0.0, 0.01)),
            frame="local_ENU",
            source="gnss",
        ),
    )
    result = backend.optimize(now_s=0.2)

    assert result.applied_delayed_measurements == 1
    assert result.replayed_events >= 4
    assert len(result.delayed_results) == 1
    assert result.delayed_results[0].accepted
    assert result.delayed_results[0].fused
    assert backend.snapshot().east_m > before + 0.4
    assert backend.last_t == pytest.approx(0.2)


def test_normal_measurement_records_explicit_normalized_timestamp():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=1.0)
    backend.predict(imu(0.0))
    backend.predict(imu(0.1))
    result = backend.update_measurement(
        "position",
        np.array([0.1, 0.0]),
        np.eye(2) * 0.1,
        frame="local_ENU",
        source="gnss",
        metadata={"normalized_timestamp_s": 0.1},
    )
    assert result.accepted
    assert backend.optimize(now_s=0.1).applied_delayed_measurements == 0


def test_out_of_sequence_direct_update_requires_delayed_path():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=1.0)
    backend.predict(imu(0.0))
    backend.predict(imu(0.2))
    with pytest.raises(FixedLagWindowError, match="requires ingest_delayed"):
        backend.update_measurement(
            "position",
            np.array([0.0, 0.0]),
            np.eye(2),
            frame="local_ENU",
            source="gnss",
            metadata={"normalized_timestamp_s": 0.1},
        )


def test_measurement_older_than_lag_is_rejected():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=0.15)
    backend.predict(imu(0.0))
    backend.predict(imu(0.1))
    backend.predict(imu(0.2))
    with pytest.raises(FixedLagWindowError):
        backend.ingest_delayed(
            source="gnss",
            timestamp_s=0.0,
            payload=DelayedMeasurement(
                kind="position",
                values=(0.0, 0.0),
                covariance=((1.0, 0.0), (0.0, 1.0)),
                frame="local_ENU",
                source="gnss",
            ),
        )


def test_delayed_payload_source_mismatch_fails_closed():
    backend = FixedLagBackendAdapter(AMEPFilter(), lag_s=1.0)
    backend.predict(imu(0.0))
    backend.predict(imu(0.1))
    with pytest.raises(ValueError, match="source argument/payload mismatch"):
        backend.ingest_delayed(
            source="radar",
            timestamp_s=0.05,
            payload=DelayedMeasurement(
                kind="position",
                values=(0.0, 0.0),
                covariance=((1.0, 0.0), (0.0, 1.0)),
                frame="local_ENU",
                source="gnss",
            ),
        )
