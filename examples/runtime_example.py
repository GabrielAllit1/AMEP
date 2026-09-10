"""Minimal AMEP-1 production-oriented integration example.

This is an interface example only. Replace synthetic measurements with validated
adapters and provide only leveled/gravity-compensated horizontal acceleration.
"""

import numpy as np

from amep1 import (
    AMEPFilter,
    AMEPRuntime,
    CommunicationsSupervisor,
    HorizontalIMUInput,
    LinkPolicy,
    build_reference_health_and_constraints,
)


def main() -> None:
    health, coverage = build_reference_health_and_constraints()
    runtime = AMEPRuntime(AMEPFilter(), health, coverage)

    comms = CommunicationsSupervisor()
    comms.register("primary_blos", LinkPolicy(priority=0, max_heartbeat_age_s=2.0))
    comms.register("secondary_blos", LinkPolicy(priority=1, max_heartbeat_age_s=5.0))

    # First IMU sample initializes the estimator timebase.
    runtime.predict(HorizontalIMUInput(0.00, 0.0, 0.0, 0.0))

    # Example 100 Hz preprocessed IMU update.
    runtime.predict(HorizontalIMUInput(0.01, 0.02, -0.01, np.deg2rad(0.2)))

    # Asynchronous aiding examples.
    runtime.update_position(timestamp_s=0.01, source="gnss", E=0.2, N=-0.1, sigma=1.5)
    runtime.update_water_velocity(timestamp_s=0.01, source="speed_log", Vw_E=1.2, Vw_N=0.1, sigma=0.15)
    runtime.update_current_prior(timestamp_s=0.01, source="current_prior", C_E=0.25, C_N=-0.05, sigma=0.2)
    runtime.update_heading(timestamp_s=0.01, source="gyrocompass", psi=np.deg2rad(87.0), sigma=np.deg2rad(0.5))

    comms.heartbeat("primary_blos", 0.01)
    status = runtime.status(0.01)
    active_link = comms.active_link(0.01)

    decision = runtime.supervisor.decide_authority(
        operator_command=None,
        autonomy_command={"desired_heading_deg": 90.0},
        has_healthy_command_link=active_link is not None,
    )

    print(status)
    print("active_link:", active_link)
    print("authority:", decision)


if __name__ == "__main__":
    main()
