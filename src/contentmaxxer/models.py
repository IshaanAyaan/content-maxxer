"""Typed shared contract for research, plans, render specs, and QA."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


SCHEMA_VERSION = "1.0"


class ClaimType(str, Enum):
    OFFICIAL_FACT = "official_fact"
    INTERPRETATION = "interpretation"
    SPECULATION = "speculation"
    UNCERTAIN = "uncertain"


@dataclass
class SourceArtifact:
    id: str
    label: str
    origin: str
    source_type: str
    retrieved_at: str
    digest: str
    normalized_path: str
    snapshot_path: str
    metadata_path: str
    status: str = "cached"


@dataclass
class Claim:
    id: str
    text: str
    evidence_excerpt: str
    source_id: str
    source_url: str
    source_label: str
    confidence: float
    claim_type: ClaimType
    numeric: bool = False

    def validate(self, source_ids: List[str]) -> List[str]:
        errors: List[str] = []
        if not self.text.strip():
            errors.append("claim text is empty")
        if not self.evidence_excerpt.strip():
            errors.append("evidence excerpt is empty")
        if self.source_id not in source_ids:
            errors.append("source_id is not present in sources")
        if not self.source_label.strip():
            errors.append("source label is empty")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        return errors


@dataclass
class VideoBeat:
    id: str
    purpose: str
    headline: str
    narration: str
    on_screen_text: str
    claim_ids: List[str]
    source_label: str
    primitive: str
    duration_seconds: float = 3.0


@dataclass
class WordTiming:
    text: str
    start_seconds: float
    end_seconds: float
    beat_id: str


@dataclass
class NarrationCue:
    beat_id: str
    text: str
    start_seconds: float
    end_seconds: float
    words: List[WordTiming] = field(default_factory=list)


@dataclass
class NarrationTrack:
    provider: str
    voice: str
    audio_path: str
    duration_seconds: float
    sample_rate: int
    alignment_method: str
    cues: List[NarrationCue] = field(default_factory=list)


@dataclass
class SlideSpec:
    id: str
    role: str
    headline: str
    body: str
    claim_ids: List[str]
    source_label: str
    visual: str
    eyebrow: str = ""
    accent_terms: List[str] = field(default_factory=list)
    transition: str = "reveal"
    engagement_trigger: str = "swipe"


@dataclass
class ContentPlan:
    id: str
    topic: str
    format: str
    hook_style: str
    hook: str
    visual_thesis: str
    source_ids: List[str]
    claims: List[Claim]
    beats: List[VideoBeat] = field(default_factory=list)
    slides: List[SlideSpec] = field(default_factory=list)
    grounded: bool = True
    blocked_reason: Optional[str] = None
    narrative_pattern: str = "claim_sequence"
    engagement_goal: str = "clarity"
    hook_candidates: List[Dict[str, Any]] = field(default_factory=list)
    angle_candidates: List[Dict[str, Any]] = field(default_factory=list)
    publishing_notes: List[str] = field(default_factory=list)
    visual_theme: str = "editorial_heat_v1"
    schema_version: str = SCHEMA_VERSION


@dataclass
class ManimPrimitiveSpec:
    kind: str
    title: str
    body: str
    claim_ids: List[str]
    source_label: str
    start_seconds: float
    duration_seconds: float
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ManimSceneSpec:
    id: str
    width: int
    height: int
    fps: int
    background: str
    safe_zone: Dict[str, int]
    caption_rail: Dict[str, int]
    primitives: List[ManimPrimitiveSpec]
    duration_seconds: float
    schema_version: str = SCHEMA_VERSION


@dataclass
class QACheck:
    name: str
    passed: bool
    detail: str
    hard: bool = True


@dataclass
class QAReport:
    artifact: str
    passed: bool
    checks: List[QACheck]
    revision: str
    schema_version: str = SCHEMA_VERSION

    @classmethod
    def from_checks(cls, artifact: str, checks: List[QACheck], revision: str) -> "QAReport":
        return cls(
            artifact=artifact,
            passed=all(check.passed for check in checks if check.hard),
            checks=checks,
            revision=revision,
        )


@dataclass
class BuildResult:
    job_dir: str
    manifest: str
    qa_passed: bool
    renderer: Optional[str] = None
