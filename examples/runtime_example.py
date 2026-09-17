"""Normalized AMEP-1 research integration example.

This example exercises the same ``MeasurementEnvelope -> ingest_measurement``
path used by the conservative research reference runtime. The numeric values are
illustrative software inputs; they are not recorded maritime sensor evidence.
"""

import numpy as np

from amep1 import (
    HorizontalIMUInput,
    MeasurementEnvelope,
    build_research_reference_runtime,
)


def measurement(
    *,
    source: str,
    kind: str,
    timestamp_s: float,
    values: tuple[float, ...],
    variance: float,
) -> MeasurementEnvelope:
    dimension = len(values)
    covariance = tuple(
        tuple(variance if row == column else 0.0 for column in range(dimension))
        for row in range(dimension)
    )
    return MeasurementEnvelope(
        source=source,
        kind=kind,
        source_timestamp_s=timestamp_s,
        receive_timestamp_s=timestamp_s + 0.01,
        values=values,
        covariance=covariance,
        frame="local_ENU",
        clock_domain="navigation",
        provenance="example.normalized-input",
        timestamp_uncertainty_s=0.001,
    )


def main() -> None:
    runtime = build_research_reference_runtime()

    runtime.predict(HorizontalIMUInput(0.00, 0.0, 0.0, 0.0))
    runtime.predict(HorizontalIMUInput(0.01, 0.02, -0.01, np.deg2rad(0.2)))

    measurements = (
        measurement(
            source="gnss",
            kind="position",
            timestamp_s=0.01,
            values=(0.2, -0.1),
            variance=1.5**2,
        ),
        measurement(
            source="speed_log",
            kind="water_velocity",
            timestamp_s=0.01,
            values=(1.2, 0.1),
            variance=0.15**2,
        ),
        measurement(
            source="current_prior",
            kind="current_prior",
            timestamp_s=0.01,
            values=(0.25, -0.05),
            variance=0.2**2,
        ),
        measurement(
            source="gyrocompass",
            kind="heading",
            timestamp_s=0.01,
            values=(np.deg2rad(87.0),),
            variance=np.deg2rad(0.5) ** 2,
        ),
    )

    for envelope in measurements:
        result = runtime.ingest_measurement(
            envelope,
            now_s=envelope.receive_timestamp_s,
        )
        print(envelope.source, result.accepted, result.reason)

    print(runtime.status(now_s=0.02))
    print(runtime.pnt_solution(now_s=0.02))


if __name__ == "__main__":
    main()
