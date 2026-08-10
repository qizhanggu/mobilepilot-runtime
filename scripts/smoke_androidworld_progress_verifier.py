"""One synthetic, device-free smoke call for the V2.2 Progress Verifier."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mobile_pilot.androidworld.progress_verifier import QwenProgressVerifier


def main() -> None:
    before = Image.new("RGB", (240, 360), "white")
    before_draw = ImageDraw.Draw(before)
    before_draw.rectangle((20, 50, 220, 110), outline="gray", width=3)
    before_draw.text((35, 70), "Contacts", fill="black")

    after = Image.new("RGB", (240, 360), "white")
    after_draw = ImageDraw.Draw(after)
    after_draw.text((25, 20), "Edit contact", fill="black")
    after_draw.rectangle((20, 65, 220, 120), outline="black", width=3)
    after_draw.text((30, 82), "Name", fill="black")
    after_draw.rectangle((20, 145, 220, 200), outline="black", width=3)
    after_draw.text((30, 162), "Phone", fill="black")
    after_draw.text((180, 320), "Save", fill="black")

    verifier = QwenProgressVerifier()
    decision = verifier.verify_with_metrics(
        before_image=before,
        after_image=after,
        action_summary="CLICK_POINT:center-right",
        task_goal="create a new contact with a name and phone number",
        subgoal="open the contact editor",
        evidence_kind="visual_state",
        evidence_value="name and phone edit fields are visible",
        trigger="synthetic_api_smoke",
        deterministic_signals={"screen_change": "meaningful_ui_change"},
    )
    print(
        json.dumps(
            {
                "verdict": decision.verdict,
                "evidence": decision.evidence,
                "disposition": decision.disposition,
                "message": decision.message,
                "metrics": asdict(decision.metrics),
                "raw_output": decision.raw_output,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    if decision.message:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
