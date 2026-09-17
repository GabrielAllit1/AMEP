# 10 — Archival Records and DOI Map

AMEP has three distinct Zenodo records. They serve different citation purposes and should not be treated as interchangeable.

| DOI | Record | Use when citing |
| --- | --- | --- |
| [10.5281/zenodo.22561851](https://doi.org/10.5281/zenodo.22561851) | Original AMEP-1 Version 1.0 research evidence | The frozen Version 1.0 research architecture, experiments, results, limitations, and historical evidence boundary. |
| [10.5281/zenodo.22818773](https://doi.org/10.5281/zenodo.22818773) | Academic v0.3.0 architecture/evidence monograph | The academic architecture and evidence description associated with AMEP v0.3.0. |
| [10.5281/zenodo.22820430](https://doi.org/10.5281/zenodo.22820430) | Exact AMEP software v0.3.0 archival release | The exact archived AMEP software implementation for release v0.3.0. |

## Citation rule

Use the record that matches the artifact or claim being discussed:

- cite **10.5281/zenodo.22561851** for the original AMEP-1 Version 1.0 research evidence and its frozen historical findings;
- cite **10.5281/zenodo.22818773** for the academic v0.3.0 architecture/evidence monograph;
- cite **10.5281/zenodo.22820430** when referring to the exact AMEP software v0.3.0 archival release.

When a statement depends on both the v0.3.0 academic description and the exact v0.3.0 implementation, cite both the monograph and software-archive records.

## Version and evidence boundary

The records are complementary, not replacements for one another. The newer v0.3.0 records do not retroactively alter the historical Version 1.0 evidence boundary. Likewise, an archival software DOI identifies a fixed software artifact; it does not by itself establish vessel, HIL, field, regulatory, certification, or operational evidence beyond what is documented for that release.

Repository `main` may continue to evolve after an archival deposit. For exact reproducibility of v0.3.0, use the software archive DOI rather than assuming a later repository checkout is identical.

## Related wiki pages

- [Verification and Evidence](06-Verification-Evidence.md)
- [Integration and Production Gates](07-Integration-Production-Gates.md)
- [Glossary, Ownership, and Citation](09-Glossary-Ownership-Citation.md)
