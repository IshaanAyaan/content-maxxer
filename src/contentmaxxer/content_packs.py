"""Curated claim packs for source-locked editorial sets."""

from typing import Dict, Iterable, List, Optional

from .models import Claim, ClaimType, SourceArtifact


GPT56_LAUNCH = "https://openai.com/index/gpt-5-6/"
GPT56_MODELS = "https://developers.openai.com/api/docs/models"
GPT56_SYSTEM_CARD = "https://deploymentsafety.openai.com/gpt-5-6"
GPT56_GUIDE = "https://developers.openai.com/api/docs/guides/latest-model"
GPT56_SOURCES = [GPT56_MODELS, GPT56_SYSTEM_CARD, GPT56_LAUNCH]
FABLE_PAGE = "https://www.anthropic.com/claude/fable"
FABLE_DOCS = "https://platform.claude.com/docs/en/about-claude/models/introducing-claude-fable-5-and-claude-mythos-5"
FABLE_COMPARISON_SOURCES = [GPT56_GUIDE, FABLE_PAGE, FABLE_DOCS]
GPT56_PACKAGED_SNAPSHOTS = {
    GPT56_LAUNCH: (
        "OpenAI GPT-5.6 launch snapshot, July 9, 2026. The GPT-5.6 family includes Sol, "
        "the flagship tier; Terra, a balanced tier for everyday work; and Luna, the most "
        "cost-efficient tier. OpenAI states that GPT-5.6 is available across ChatGPT, Codex, "
        "and the OpenAI API, with exact access depending on product and subscription plan. "
        "OpenAI describes these as durable capability tiers that can advance independently."
    ),
    GPT56_MODELS: (
        "OpenAI model documentation snapshot, July 9, 2026. Start with GPT-5.6 Sol for complex "
        "reasoning and coding, choose GPT-5.6 Terra to balance intelligence and cost, or use "
        "GPT-5.6 Luna for cost-sensitive, high-volume workloads. The model IDs are gpt-5.6-sol, "
        "gpt-5.6-terra, and gpt-5.6-luna."
    ),
    GPT56_SYSTEM_CARD: (
        "OpenAI GPT-5.6 System Card snapshot, July 9, 2026. OpenAI treats Sol, Terra, and Luna "
        "as High capability in Biological and Chemical risk and in Cybersecurity, while below "
        "Critical. OpenAI describes layered safeguards including protections trained into the "
        "model, real-time checks, monitoring, and account-level enforcement. OpenAI reports that "
        "Sol cyber safeguards block roughly ten times more potentially harmful activity and says "
        "the controls can create friction for benign users while aiming to preserve legitimate work."
    ),
}

FABLE_COMPARISON_SNAPSHOTS = {
    GPT56_GUIDE: (
        "OpenAI GPT-5.6 model guide snapshot, July 10, 2026. GPT-5.6 Sol is the frontier tier, "
        "Terra balances intelligence and cost, and Luna is optimized for efficient high-volume work. "
        "Sol has a 1.05 million token context window, a 128,000 token maximum output, and list pricing "
        "of $5 per million input tokens and $30 per million output tokens. GPT-5.6 supports reasoning "
        "effort levels from none through max, plus a pro mode for the hardest work."
    ),
    FABLE_PAGE: (
        "Anthropic Claude Fable 5 product page snapshot, July 10, 2026. Anthropic describes Fable 5 as "
        "its most ambitious model for the hardest coding and professional work. The listed model ID is "
        "claude-fable-5. List pricing is $10 per million input tokens and $50 per million output tokens."
    ),
    FABLE_DOCS: (
        "Anthropic platform documentation snapshot, July 10, 2026. Fable 5 is Anthropic's most capable "
        "widely released model for demanding reasoning and long-horizon agentic work. It has a one million "
        "token context window and 128,000 token maximum output. Adaptive thinking is always on. Anthropic "
        "also notes that safety classifiers can decline some requests and documents fallback options."
    ),
}


def _source(sources: Iterable[SourceArtifact], preferred: str) -> Optional[SourceArtifact]:
    items = list(sources)
    for item in items:
        if item.origin.rstrip("/") == preferred.rstrip("/"):
            return item
    domain = preferred.split("/")[2]
    return next((item for item in items if domain in item.origin), items[0] if items else None)


def _claim(
    claim_id: str,
    text: str,
    excerpt: str,
    source: SourceArtifact,
    claim_type: ClaimType = ClaimType.OFFICIAL_FACT,
    numeric: bool = False,
    confidence: float = 0.98,
    source_label_override: Optional[str] = None,
) -> Claim:
    return Claim(
        id=claim_id,
        text=text,
        evidence_excerpt=excerpt,
        source_id=source.id,
        source_url=source.origin,
        source_label=source_label_override or source.label,
        confidence=confidence,
        claim_type=claim_type,
        numeric=numeric,
    )


def gpt56_claims(topic: str, sources: List[SourceArtifact]) -> Optional[List[Claim]]:
    key = topic.lower().replace("-", "_").replace(" ", "_")
    if "gpt" not in key or "5" not in key or "6" not in key:
        return None
    if "fable" in key:
        guide = _source(sources, GPT56_GUIDE)
        fable_page = _source(sources, FABLE_PAGE)
        fable_docs = _source(sources, FABLE_DOCS)
        if not guide or not fable_page or not fable_docs:
            return None
        return [
            _claim(
                "clm_fable_position",
                "Anthropic positions Fable 5 as its most capable widely released model for demanding reasoning and long-horizon agentic work.",
                "Fable 5 is Anthropic's most capable widely released model for demanding reasoning and long-horizon agentic work.",
                fable_docs,
            ),
            _claim(
                "clm_fable_price",
                "Fable 5 list pricing is $10 per million input tokens and $50 per million output tokens.",
                "List pricing is $10 per million input tokens and $50 per million output tokens.",
                fable_page,
                numeric=True,
            ),
            _claim(
                "clm_fable_context",
                "Fable 5 has a one-million-token context window and a 128,000-token maximum output.",
                "Fable 5 has a one million token context window and 128,000 token maximum output.",
                fable_docs,
                numeric=True,
            ),
            _claim(
                "clm_fable_adaptive",
                "Fable 5 uses always-on adaptive thinking.",
                "Adaptive thinking is always on.",
                fable_docs,
            ),
            _claim(
                "clm_fable_safety",
                "Anthropic says Fable 5 safety classifiers can decline some requests and documents fallback options.",
                "Safety classifiers can decline some requests; fallback options are documented.",
                fable_docs,
            ),
            _claim(
                "clm_gpt_family",
                "GPT-5.6 is a three-tier family: Sol, Terra, and Luna.",
                "Sol is the frontier tier, Terra balances intelligence and cost, and Luna targets efficient high-volume work.",
                guide,
            ),
            _claim(
                "clm_gpt_sol_price",
                "GPT-5.6 Sol list pricing is $5 per million input tokens and $30 per million output tokens.",
                "Sol list pricing is $5 per million input tokens and $30 per million output tokens.",
                guide,
                numeric=True,
            ),
            _claim(
                "clm_gpt_sol_context",
                "GPT-5.6 Sol has a 1.05-million-token context window and a 128,000-token maximum output.",
                "Sol has a 1.05 million token context window and a 128,000 token maximum output.",
                guide,
                numeric=True,
            ),
            _claim(
                "clm_gpt_effort",
                "GPT-5.6 exposes reasoning effort levels from none through max, plus a pro mode.",
                "GPT-5.6 supports reasoning effort from none through max, plus a pro mode.",
                guide,
            ),
            _claim(
                "clm_comparison_interpretation",
                "Fable 5 is a single frontier bet, while GPT-5.6 is a tiered system with more explicit effort controls.",
                "The official documentation presents Fable 5 as one frontier model and GPT-5.6 as Sol, Terra, and Luna with selectable effort.",
                guide,
                claim_type=ClaimType.INTERPRETATION,
                confidence=0.9,
                source_label_override="CONTENTMAXXER ANALYSIS · OFFICIAL SPECS",
            ),
            _claim(
                "clm_cost_interpretation",
                "Token price is only one component of production economics; the useful operating metric is cost per successful task.",
                "Editorial analysis derived from the official list prices and model operating differences; validate with production task outcomes.",
                guide,
                claim_type=ClaimType.INTERPRETATION,
                confidence=0.82,
                source_label_override="CONTENTMAXXER ANALYSIS · OFFICIAL PRICES",
            ),
        ]
    launch = _source(sources, GPT56_LAUNCH)
    models = _source(sources, GPT56_MODELS)
    card = _source(sources, GPT56_SYSTEM_CARD)
    if not launch or not models or not card:
        return None

    family = [
        _claim(
            "clm_family_three",
            "OpenAI launched GPT-5.6 as a three-model family: Sol, Terra, and Luna.",
            "The GPT-5.6 family includes the flagship Sol, balanced Terra, and cost-efficient Luna.",
            launch,
        ),
        _claim(
            "clm_tier_roles",
            "Sol is the flagship tier, Terra balances capability and cost, and Luna targets cost-sensitive high-volume work.",
            "Choose Sol for complex work, Terra for balance, or Luna for cost-sensitive high-volume workloads.",
            models,
        ),
        _claim(
            "clm_available_surfaces",
            "OpenAI says GPT-5.6 is available across ChatGPT, Codex, and the OpenAI API.",
            "GPT-5.6 is available across ChatGPT, Codex, and the OpenAI API.",
            launch,
        ),
        _claim(
            "clm_plan_qualified",
            "Exact model and effort options vary by product and subscription plan.",
            "ChatGPT and Codex access differs for Free, Go, Plus, Pro, Business, and Enterprise users.",
            launch,
        ),
        _claim(
            "clm_api_models",
            "The API exposes distinct Sol, Terra, and Luna model IDs.",
            "The documented IDs are gpt-5.6-sol, gpt-5.6-terra, and gpt-5.6-luna.",
            models,
        ),
        _claim(
            "clm_family_interpretation",
            "The release is best understood as a tiered model-family story, not a single-model update.",
            "OpenAI describes three durable capability tiers that can advance on their own cadence.",
            launch,
            claim_type=ClaimType.INTERPRETATION,
            confidence=0.9,
        ),
    ]
    safety = [
        _claim(
            "clm_high_designation",
            "OpenAI treats Sol, Terra, and Luna as High capability in Biological and Chemical risk and in Cybersecurity.",
            "All three models are designated High in Biological and Chemical risk and High in Cybersecurity.",
            card,
        ),
        _claim(
            "clm_below_critical",
            "OpenAI says the models do not reach the Critical threshold in cyber or biological/chemical risk.",
            "None of the three models need to be treated as Critical in these tracked categories.",
            card,
        ),
        _claim(
            "clm_layered_safeguards",
            "OpenAI describes safeguards that combine model protections, real-time checks, monitoring, and account-level enforcement.",
            "The safety system layers model protections with real-time checks, monitoring, and account-level enforcement.",
            card,
        ),
        _claim(
            "clm_ten_times",
            "OpenAI reports that Sol cyber safeguards block roughly ten times more potentially harmful activity than previous models.",
            "Sol cyber safeguards block roughly ten times more potentially harmful activity.",
            card,
            numeric=True,
        ),
        _claim(
            "clm_benign_friction",
            "OpenAI acknowledges that stronger safeguards can create friction for benign users.",
            "These measures can create friction for benign users.",
            card,
        ),
        _claim(
            "clm_controls_interpretation",
            "The GPT-5.6 safety story is a tradeoff between stronger controls and preserving legitimate defensive work.",
            "OpenAI says it aims to block serious misuse while enabling legitimate defensive work.",
            card,
            claim_type=ClaimType.INTERPRETATION,
            confidence=0.89,
        ),
    ]
    if any(word in key for word in ("capability", "control", "safety", "cyber", "bio")):
        return safety
    return family


def editorial_title(topic: str) -> Optional[str]:
    key = topic.lower().replace("-", "_").replace(" ", "_")
    if "gpt" not in key or "5" not in key or "6" not in key:
        return None
    if any(word in key for word in ("capability", "control", "safety", "cyber", "bio")):
        return "GPT-5.6 is capability plus controls"
    return "GPT-5.6 is a three-tier family"
