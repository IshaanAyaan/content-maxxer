"""Optional planning-provider seam; deterministic planning remains the default."""

from typing import List, Protocol

from .models import Claim, ContentPlan, SourceArtifact


class PlanningProvider(Protocol):
    def plan(self, topic: str, sources: List[SourceArtifact], claims: List[Claim], format: str) -> ContentPlan:
        """Return a source-grounded plan without mutating the source cache."""


class DeterministicProvider:
    """Marker used in manifests for the built-in, no-API planning path."""

    name = "deterministic_claim_pack"
