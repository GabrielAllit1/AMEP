import numpy as np

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    ConstraintCoverage,
    ConstraintSpec,
    FixedLagBackendAdapter,
    HorizontalIMUInput,
    MeasurementEnvelope,
    SensorHealth,
    SensorHealthManager,
    SourcePolicy,
    ingest_delayed_measurement,
)


def build_runtime(lag_s=1.0):
    health = SensorHealthManager()
    health.register("gnss", SourcePolicy(max_age_s=1.0))
    coverage = ConstraintCoverage()
    coverage.register(
        "gnss",
        ConstraintSpec((0, 1), absolute_position=True, gnss=True),
    )
    estimator = FixedLagBackendAdapter(AMEPFilter(P=np.eye(7)), lag_s=lag_s)
    return AMEPRuntime(estimator, health, coverage)


def predict_to(runtime, *timestamps):
    for timestamp in timestamps:
        runtime.predict(HorizontalIMUInput(timestamp, 0.0, 0.0, 0.0))


def position_envelope(timestamp, receive, east, north, sigma=0.2):
    variance = sigma**2
    return MeasurementEnvelope(
        source="gnss",
        kind="position",
        source_timestamp_s=timestamp,
        receive_timestamp_s=receive,
        values=(east, north),
        covariance=((variance, 0.0), (0.0, variance)),
    )


def test_delayed_runtime_path_rewinds_without_health_time_regression():
    runtime = build_runtime()
    predict_to(runtime, 0.0, 0.1, 0.2)

    current = runtime.ingest_measurement(position_envelope(0.2, 0.2, 0.0, 0.0))
    assert current.accepted
    assert runtime.health.state("gnss") == SensorHealth.ONLINE
    assert runtime.health.source_ages(0.2)["gnss"] == 0.0

    delayed = ingest_delayed_measurement(
        runtime,
        position_envelope(0.1, 0.2, 0.3, 0.0),
        now_s=0.2,
    )

    assert delayed.accepted
    assert delayed.measurement_result is not None
    assert delayed.measurement_result.accepted
    assert delayed.reason.startswith("delayed_")
    assert runtime.health.state("gnss") == SensorHealth.ONLINE
    # The historical sample contributes to health statistics but cannot move
    # the source freshness watermark backward from the 0.2 s current sample.
    assert runtime.health.source_ages(0.2)["gnss"] == 0.0
    assert runtime.estimator.last_t == 0.2


def test_normal_ingest_still_rejects_out_of_order_measurement():
    runtime = build_runtime()
    predict_to(runtime, 0.0, 0.1, 0.2)
    assert runtime.ingest_measurement(position_envelope(0.2, 0.2, 0.0, 0.0)).accepted

    rejected = runtime.ingest_measurement(position_envelope(0.1, 0.2, 0.1, 0.0))
    assert not rejected.accepted
    assert rejected.reason == "out_of_order_measurement"


def test_delayed_helper_requires_fixed_lag_backend():
    health = SensorHealthManager()
    health.register("gnss", SourcePolicy(max_age_s=1.0))
    coverage = ConstraintCoverage()
    runtime = AMEPRuntime(AMEPFilter(), health, coverage)

    rejected = ingest_delayed_measurement(
        runtime,
        position_envelope(0.0, 0.1, 0.0, 0.0),
    )
    assert not rejected.accepted
    assert rejected.reason == "delayed_backend_not_configured"


def test_fixed_lag_window_remains_fail_closed_through_runtime():
    runtime = build_runtime(lag_s=0.1)
    predict_to(runtime, 0.0, 0.1, 0.2, 0.3)

    rejected = ingest_delayed_measurement(
        runtime,
        position_envelope(0.0, 0.3, 0.0, 0.0),
        now_s=0.3,
    )
    assert not rejected.accepted
    assert rejected.reason.startswith("delayed_measurement_contract_rejected:")
