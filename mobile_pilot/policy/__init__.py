"""候选动作、Grounding 和旧视觉策略适配。"""

from .grounding import Grounder, GroundingCandidate, GroundingSource, PointTarget, SemanticTarget
from .gui_plus import GuiPlusDecision, GuiPlusRequest, GuiPlusVisionPolicy, VisionCallMetrics, parse_gui_plus_output
from .hybrid import GroundingMode, HybridGrounder
from .legacy_vision import LegacyVisionPolicy

__all__ = [
    "Grounder",
    "GroundingCandidate",
    "GroundingSource",
    "GroundingMode",
    "GuiPlusRequest",
    "GuiPlusDecision",
    "GuiPlusVisionPolicy",
    "HybridGrounder",
    "LegacyVisionPolicy",
    "PointTarget",
    "SemanticTarget",
    "VisionCallMetrics",
    "parse_gui_plus_output",
]
