# Showcase asset provenance

These files are presentation assets layered on top of the immutable experiment tag `mobilepilot-v2.2-final`.

- `architecture.svg` summarizes the implemented runtime call chain.
- `project-journey.svg` uses the recorded V1/V2/V2.1/V2.2 development and frozen results.
- `frozen-results.svg` uses values recomputed in `docs/final/audit/audit-metrics.json`.
- `recovery-case-study.svg` is reconstructed from the frozen `MarkorDeleteNewestNote` JSONL events. Only the second Recovery episode is labeled as a strict rescue.
- `social-preview.svg` is the editable bilingual source for `social-preview.png`: the project name and technical positioning stay in English, while the value statement and scope boundary are shown in Chinese for domestic interview review.

The frozen Markor trace contains only the launcher-to-Markor verifier image pair, not the later Delete/OK dialog frames. The case-study asset therefore uses a Trace event flow rather than invented screenshots. No synthetic phone UI is presented as experiment evidence.
