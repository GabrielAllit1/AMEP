# Security and Safety Reporting

AMEP is research software for navigation-estimation and autonomy-authority experiments. It is not approved for operational vessel navigation, certified PNT, collision avoidance, or safety-critical control.

## Reporting

Report security, data-integrity, dependency, command-authority, timing, or fail-safe defects privately to the repository owner rather than publishing exploit details in a public issue before remediation.

Particularly important defect classes include:

- acceptance of malformed or non-finite navigation measurements;
- timebase rollback or timestamp manipulation that bypasses fail-closed behavior;
- sensor isolation/recovery paths that allow untrusted data to fuse unexpectedly;
- authority logic that permits autonomy in `SAFE_HOLD` or otherwise bypasses navigation-mode restrictions;
- covariance or numerical failures that produce silently invalid confidence estimates;
- dependency or supply-chain compromise;
- command/telemetry link handling that produces ambiguous operator authority.

## Operational warning

Do not use this repository as the sole navigation or control system for a real vessel. Operational deployment requires independent engineering, safety analysis, validated hardware/interfaces, environmental testing, cybersecurity controls, and applicable regulatory/standards work.
