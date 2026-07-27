"""Deterministic, claim-led planning for reels and carousels."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .content_packs import editorial_title, gpt56_claims
from .io import digest_text, write_json
from .models import Claim, ClaimType, ContentPlan, SlideSpec, SourceArtifact, VideoBeat
from .sources import read_normalized_source


HOOK_STYLES = ("direct", "question", "contrarian", "statistic", "curiosity", "story", "list")
PRIMITIVES = (
    "model_cards",
    "timeline",
    "comparison_grid",
    "tokens_context",
    "eval_bars",
    "agent_loop",
    "claim_callout",
    "routing_diagram",
    "before_after",
)


class PlanningError(RuntimeError):
    pass


def _sentences(text: str) -> List[str]:
    without_markdown_headings = re.sub(r"(?m)^\s{0,3}#{1,6}\s+.*$", " ", text)
    without_reference_lines = re.sub(
        r"(?im)^\s*(?:[-*]\s*)?(?:primary\s+)?(?:references?|sources?)\s*:.*$",
        " ",
        without_markdown_headings,
    )
    without_url_lines = re.sub(r"(?m)^\s*(?:[-*]\s*)?.*https?://\S+.*$", " ", without_reference_lines)
    compact = re.sub(r"\s+", " ", without_url_lines).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
    return [
        part.strip()
        for part in parts
        if 35 <= len(part.strip()) <= 420
        and "http://" not in part.lower()
        and "https://" not in part.lower()
        and not re.match(r"^(?:primary\s+)?(?:references?|sources?)\s*:", part, re.I)
    ]


def _topic_tokens(topic: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", topic.lower()) if len(token) > 2]


def extract_claims(topic: str, job_dir: Path, sources: List[SourceArtifact], limit: int = 12) -> List[Claim]:
    packed = gpt56_claims(topic, sources)
    if packed is not None:
        return packed
    tokens = _topic_tokens(topic)
    candidates = []
    for source_index, source in enumerate(sources):
        sentences = _sentences(read_normalized_source(job_dir, source))
        relevant_positions = {
            position
            for position, sentence in enumerate(sentences)
            if not tokens or any(token in sentence.lower() for token in tokens)
        }
        context_positions = {
            context
            for position in relevant_positions
            for context in range(max(0, position - 1), min(len(sentences), position + 3))
        }
        for position, sentence in enumerate(sentences):
            lower = sentence.lower()
            relevance = sum(1 for token in tokens if token in lower)
            if tokens and position not in context_positions:
                continue
            nav_penalty = sum(1 for term in ("cookie", "privacy", "sign in", "subscribe", "menu") if term in lower)
            if nav_penalty:
                continue
            candidates.append((source_index, position, relevance, source, sentence))
    # Source notes are usually written in explanatory order. Relevance decides
    # which local context to keep, but should not scramble that narrative.
    candidates.sort(key=lambda item: (item[0], item[1], -item[2]))
    claims: List[Claim] = []
    seen = set()
    for _, _, _, source, sentence in candidates:
        normalized = sentence.rstrip(" .")
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        numeric = bool(re.search(r"(?:\d[\d,.]*\s*%|\$\s*\d|\b\d+(?:\.\d+)?x\b)", normalized, re.I))
        official = any(host in source.origin for host in ("openai.com", ".gov", ".edu"))
        claims.append(
            Claim(
                id="clm_" + digest_text(source.id + normalized)[:10],
                text=normalized + ".",
                evidence_excerpt=normalized[:280],
                source_id=source.id,
                source_url=source.origin,
                source_label=source.label,
                confidence=0.9 if official else 0.72,
                claim_type=ClaimType.OFFICIAL_FACT if official else ClaimType.UNCERTAIN,
                numeric=numeric,
            )
        )
        if len(claims) >= limit:
            break
    return claims


def validate_claims(claims: Sequence[Claim], sources: Sequence[SourceArtifact]) -> List[str]:
    source_ids = [source.id for source in sources]
    errors: List[str] = []
    ids = set()
    for claim in claims:
        if claim.id in ids:
            errors.append(f"{claim.id}: duplicate claim id")
        ids.add(claim.id)
        errors.extend(f"{claim.id}: {error}" for error in claim.validate(source_ids))
    return errors


def write_claim_map(job_dir: Path, sources: Sequence[SourceArtifact], claims: Sequence[Claim]) -> Path:
    errors = validate_claims(claims, sources)
    path = job_dir / "claims.json"
    write_json(path, {"schema_version": "1.0", "valid": not errors, "errors": errors, "claims": list(claims)})
    return path


def _hook(topic: str, style: str, claims: Sequence[Claim]) -> str:
    if style not in HOOK_STYLES:
        raise PlanningError(f"unknown hook style: {style}")
    first = claims[0].text.rstrip(".")
    title = editorial_title(topic) or first
    if style == "direct":
        return title + "."
    if style == "question":
        clean_topic = topic.strip().rstrip(".?!")
        why_match = re.match(r"^why\s+([A-Za-z][\w-]*)\s+(.+)$", clean_topic, re.I)
        if why_match and why_match.group(1).lower() not in {"do", "does", "did", "can", "is", "are", "will"}:
            subject, predicate = why_match.groups()
            auxiliary = "do" if subject.lower().endswith("s") else "does"
            if auxiliary == "does":
                predicate = re.sub(r"^([A-Za-z]+)s\b", r"\1", predicate)
            clean_topic = f"Why {auxiliary} {subject} {predicate}"
        how_match = re.match(r"^how\s+(.+?)\s+([A-Za-z]+s)\b(.*)$", clean_topic, re.I)
        if how_match and not re.match(r"^how\s+(?:do|does|did|can|is|are|will)\b", clean_topic, re.I):
            subject, verb, rest = how_match.groups()
            clean_topic = f"How does {subject} {verb[:-1]}{rest}"
        if re.match(r"^(why|how|what|when|where|can|does|do|is|are)\b", clean_topic, re.I):
            return clean_topic[0].upper() + clean_topic[1:] + "?"
        return f"How does {clean_topic} actually work?"
    if style == "contrarian":
        return f"The simple version misses the point: {title.rstrip('.')}"
    if style == "statistic":
        numeric = next((claim for claim in claims if claim.numeric), None)
        if numeric is None:
            raise PlanningError("statistic hooks require a numeric source-backed claim")
        return numeric.text
    if style == "curiosity":
        return f"The detail most summaries miss: {title.rstrip('.')}"
    if style == "story":
        return f"One release, one source trail, and a bigger story: {title.rstrip('.')}"
    return f"Three things the sources establish about {topic}."


def _ordered_for_hook(style: str, claims: Sequence[Claim]) -> List[Claim]:
    ordered = list(claims)
    if style == "statistic":
        numeric = next((claim for claim in ordered if claim.numeric), None)
        if numeric is not None:
            ordered = [numeric] + [claim for claim in ordered if claim.id != numeric.id]
    return ordered


def _words(value: str, limit: int) -> str:
    clean = " ".join(value.replace("GPT-5.6", "GPT‑5.6").split()).rstrip(".")
    parts = clean.split()
    return " ".join(parts[:limit]).rstrip(".,;:") + ("…" if len(parts) > limit else "")


def _hook_score(text: str, style: str, numeric: bool = False) -> Dict[str, int]:
    word_count = len(text.split())
    clarity = 10 if word_count <= 10 else max(4, 20 - word_count)
    curiosity = 9 if any(token in text for token in ("WHY", "HOW", "MISSED", "TRADEOFF", "?", "ISN’T")) else 7
    specificity = 10 if numeric or any(token in text for token in ("SOL", "TERRA", "LUNA", "GPT")) else 7
    swipe = 10 if any(token in text for token in ("HERE", "THIS", "WHY", "DIFFERENCE", "PICKER", "BREAKDOWN", "ISN’T")) else 8
    return {"clarity": clarity, "curiosity": curiosity, "specificity": specificity, "swipe_potential": swipe}


def _candidate(text: str, style: str, claim_ids: Sequence[str], numeric: bool = False) -> Dict[str, Any]:
    scores = _hook_score(text, style, numeric=numeric)
    return {
        "text": text,
        "style": style,
        "claim_ids": list(claim_ids),
        **scores,
        "score": sum(scores.values()),
    }


def _hook_candidates(topic: str, claims: Sequence[Claim]) -> List[Dict[str, Any]]:
    key = topic.lower().replace("-", "_").replace(" ", "_")
    if "fable" in key and "gpt" in key and any(word in key for word in ("cost", "price", "economics")):
        fable = next(claim for claim in claims if claim.id == "clm_fable_price")
        gpt = next(claim for claim in claims if claim.id == "clm_gpt_sol_price")
        hooks = [
            ("100M OUTPUT TOKENS: A $2,000 LIST-PRICE GAP.", "statistic", [fable.id, gpt.id], True),
            ("FABLE 5 VS GPT‑5.6: THE COST GAP IS REAL.", "direct", [fable.id, gpt.id], True),
            ("SAME 128K OUTPUT CEILING. VERY DIFFERENT PRICE TAG.", "contrast", [fable.id, gpt.id], True),
            ("THE MODEL BILL ISN’T THE REAL MODEL COST.", "contrarian", [fable.id, gpt.id], False),
            ("WOULD YOU PAY $2,000 MORE FOR 100M OUTPUT TOKENS?", "question", [fable.id, gpt.id], True),
            ("FABLE 5 OUTPUT COSTS 67% MORE THAN SOL.", "statistic", [fable.id, gpt.id], True),
            ("THE AI PRICE COMPARISON EVERY BUILDER SHOULD SAVE.", "save", [fable.id, gpt.id], False),
            ("WHY CHEAPER TOKENS CAN STILL COST MORE.", "question", [fable.id, gpt.id], False),
            ("FABLE 5: $50 OUT. GPT‑5.6 SOL: $30.", "list", [fable.id, gpt.id], True),
            ("DON’T PICK A MODEL FROM TOKEN PRICE ALONE.", "contrarian", [fable.id, gpt.id], False),
            ("THE REAL METRIC IS COST PER SUCCESSFUL TASK.", "direct", [fable.id, gpt.id], False),
            ("SAVE THIS BEFORE YOUR NEXT MODEL MIGRATION.", "save", [fable.id, gpt.id], False),
        ]
        return [_candidate(*item) for item in hooks]
    if "fable" in key and "gpt" in key:
        fable = next(claim for claim in claims if claim.id == "clm_fable_position")
        gpt = next(claim for claim in claims if claim.id == "clm_gpt_family")
        hooks = [
            ("FABLE 5 VS GPT‑5.6 ISN’T A NORMAL MODEL FIGHT.", "direct", [fable.id, gpt.id], False),
            ("ONE FRONTIER BET VS AN ENTIRE MODEL SYSTEM.", "contrast", [fable.id, gpt.id], False),
            ("FABLE 5 OR GPT‑5.6? YOU’RE ASKING THE WRONG QUESTION.", "contrarian", [fable.id, gpt.id], False),
            ("THEIR CONTEXT WINDOWS ARE ALMOST IDENTICAL.", "curiosity", [fable.id, gpt.id], True),
            ("FABLE 5 COSTS MORE. GPT‑5.6 GIVES MORE CONTROL.", "contrast", [fable.id, gpt.id], True),
            ("WHICH FRONTIER MODEL ACTUALLY FITS YOUR WORKFLOW?", "question", [fable.id, gpt.id], False),
            ("THE MODEL WAR JUST BECAME A SYSTEMS WAR.", "news", [fable.id, gpt.id], False),
            ("ONE MODEL. THREE TIERS. TWO VERY DIFFERENT BETS.", "list", [fable.id, gpt.id], False),
            ("STOP ASKING WHICH MODEL ‘WINS.’", "contrarian", [fable.id, gpt.id], False),
            ("THE FABLE 5 VS GPT‑5.6 BREAKDOWN WORTH SAVING.", "save", [fable.id, gpt.id], False),
            ("WHY GPT‑5.6 FEELS LIKE INFRASTRUCTURE, NOT A MODEL.", "question", [gpt.id], False),
            ("SAVE THIS MODEL PICKER BEFORE YOU SWITCH.", "save", [fable.id, gpt.id], False),
        ]
        return [_candidate(*item) for item in hooks]
    if "gpt" in key and "5" in key and "6" in key and any(word in key for word in ("capability", "control", "safety", "cyber", "bio")):
        numeric = next((claim for claim in claims if claim.numeric), claims[0])
        friction = next((claim for claim in claims if claim.id == "clm_benign_friction"), numeric)
        hooks = [
            ("GPT‑5.6 BLOCKS ~10× MORE. HERE’S THE TRADEOFF.", "statistic", [numeric.id, friction.id], True),
            ("GPT‑5.6 GOT STRONGER. SO DID THE GUARDRAILS.", "contrast", [claims[0].id], False),
            ("OPENAI’S GPT‑5.6 SAFETY BET IS MORE AGGRESSIVE.", "news", [numeric.id], True),
            ("“HIGH” CAPABILITY DOESN’T MEAN “CRITICAL.”", "contrarian", [claims[0].id, claims[1].id], False),
            ("THE SAFETY STORY ISN’T JUST MORE BLOCKING.", "curiosity", [numeric.id, friction.id], True),
            ("WHY GPT‑5.6 MAY FEEL MORE RESTRICTIVE.", "question", [friction.id], False),
            ("STRONGER CONTROLS. MORE BENIGN FRICTION.", "contrast", [friction.id], False),
            ("GPT‑5.6 HAS FOUR LAYERS OF DEFENSE.", "list", [claims[2].id], False),
            ("OPENAI IS TRADING CONVENIENCE FOR CONTROL.", "tension", [friction.id], False),
            ("THE REAL GPT‑5.6 STORY IS CAPABILITY + CONTROL.", "direct", [claims[-1].id], False),
            ("WOULD YOU ACCEPT MORE FRICTION FOR MORE SAFETY?", "question", [friction.id], False),
            ("SAVE THIS GPT‑5.6 SAFETY BREAKDOWN.", "save", [claims[-1].id], False),
        ]
        return [_candidate(*item) for item in hooks]
    if "gpt" in key and "5" in key and "6" in key:
        first = claims[0]
        hooks = [
            ("GPT‑5.6 ISN’T ONE MODEL. IT’S THREE.", "direct", [first.id], False),
            ("OPENAI JUST SPLIT GPT‑5.6 INTO THREE TIERS.", "news", [first.id], False),
            ("SOL, TERRA, LUNA: HERE’S THE DIFFERENCE.", "list", [first.id, claims[1].id], False),
            ("PICKING GPT‑5.6 NOW MEANS PICKING A TIER.", "consequence", [claims[1].id], False),
            ("THE GPT‑5.6 NAME HIDES THREE DIFFERENT JOBS.", "curiosity", [claims[1].id], False),
            ("WHICH GPT‑5.6 TIER ACTUALLY FITS YOU?", "question", [claims[1].id], False),
            ("ONE FAMILY. THREE PRICE‑PERFORMANCE BETS.", "contrast", [first.id, claims[1].id], False),
            ("GPT‑5.6 CHANGED HOW YOU CHOOSE A MODEL.", "consequence", [claims[1].id], False),
            ("STOP TREATING GPT‑5.6 LIKE ONE MODEL.", "contrarian", [first.id], False),
            ("THE GPT‑5.6 DETAIL EVERYONE MISSED.", "curiosity", [first.id], False),
            ("BEFORE YOU PICK GPT‑5.6, SEE THIS.", "direct", [claims[1].id], False),
            ("SAVE THIS GPT‑5.6 MODEL PICKER.", "save", [claims[1].id], False),
        ]
        return [_candidate(*item) for item in hooks]
    first = claims[0]
    subject = _words(topic.upper(), 5)
    fact = _words(first.text.upper(), 10)
    hooks = [
        (fact, "direct"),
        (f"THE {subject} DETAIL MOST PEOPLE MISS.", "curiosity"),
        (f"WHAT CHANGED IN {subject}—AND WHY IT MATTERS.", "news"),
        (f"STOP SCROLLING: {fact}", "direct"),
        (f"WHY {subject} ISN’T AS SIMPLE AS IT LOOKS.", "question"),
        (f"THE SOURCE-BACKED {subject} BREAKDOWN.", "list"),
        (f"ONE {subject} FACT WORTH SAVING.", "save"),
        (f"THE OLD {subject} MENTAL MODEL IS INCOMPLETE.", "contrarian"),
        (f"HERE’S WHAT THE {subject} HEADLINE LEAVES OUT.", "curiosity"),
        (f"{subject}: THE MECHANISM IN 30 SECONDS.", "mechanism"),
        (f"WHAT THE PRIMARY SOURCE ACTUALLY SAYS ABOUT {subject}.", "proof"),
        (f"SAVE THIS BEFORE YOU EXPLAIN {subject}.", "save"),
    ]
    return [_candidate(text, style, [first.id], numeric=first.numeric) for text, style in hooks]


def _angle_candidates(topic: str) -> List[Dict[str, Any]]:
    return [
        {"angle": "news", "promise": "What changed, in one sharp headline", "score": 88},
        {"angle": "mechanism", "promise": "The mental model the announcement did not visualize", "score": 94},
        {"angle": "tension", "promise": "The benefit-versus-tradeoff that earns discussion", "score": 91},
    ]


def _pick_hook(hook_style: str, candidates: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    aliases = {
        "direct": "direct",
        "statistic": "statistic",
        "question": "question",
        "contrarian": "contrarian",
        "curiosity": "curiosity",
        "list": "list",
        "story": "news",
    }
    wanted = aliases.get(hook_style)
    matching = [item for item in candidates if wanted and item["style"] == wanted]
    pool = matching or list(candidates)
    return max(pool, key=lambda item: (item["score"], -len(item["text"])))


def _claim_lookup(claims: Sequence[Claim]) -> Dict[str, Claim]:
    return {claim.id: claim for claim in claims}


def _slide(
    index: int,
    role: str,
    headline: str,
    body: str,
    claim_ids: Sequence[str],
    claims: Sequence[Claim],
    visual: str,
    eyebrow: str,
    accent_terms: Sequence[str],
    transition: str,
    trigger: str,
) -> SlideSpec:
    lookup = _claim_lookup(claims)
    source_label = lookup[claim_ids[0]].source_label if claim_ids else ""
    return SlideSpec(
        id=f"slide_{index:02d}",
        role=role,
        headline=headline,
        body=body,
        claim_ids=list(claim_ids),
        source_label=source_label,
        visual=visual,
        eyebrow=eyebrow,
        accent_terms=list(accent_terms),
        transition=transition,
        engagement_trigger=trigger,
    )


def _gpt56_story(topic: str, claims: Sequence[Claim]) -> List[SlideSpec]:
    key = topic.lower()
    by_id = _claim_lookup(claims)
    if "fable" in key and any(word in key for word in ("cost", "price", "economics")):
        raw = [
            ("hook", "100M OUTPUT TOKENS: A $2,000 LIST-PRICE GAP.", "Two frontier models. One bill your spreadsheet will notice.", ["clm_fable_price", "clm_gpt_sol_price"], "calculator_receipt", "MODEL ECONOMICS", ["$2,000", "GAP"], "open_loop", "swipe for the math"),
            ("lock_in", "FABLE 5: $50 PER MILLION OUT.", "At 100 million output tokens, the list-price total is $5,000.", ["clm_fable_price"], "price_fable", "THE EXPENSIVE LINE", ["$50", "$5,000"], "reveal", "start the receipt"),
            ("reveal", "GPT‑5.6 SOL: $30 PER MILLION OUT.", "The same output volume lists at $3,000.", ["clm_gpt_sol_price"], "price_gpt", "THE OTHER LINE", ["$30", "$3,000"], "contrast", "compare the bill"),
            ("mechanism", "INPUT IS $10 VS $5.", "Fable 5 also lists at twice Sol’s input-token price.", ["clm_fable_price", "clm_gpt_sol_price"], "input_split", "THE SECOND GAP", ["$10", "$5"], "mechanism", "complete the math"),
            ("proof", "CONTEXT IS NEARLY A TIE.", "Fable: 1M. Sol: 1.05M. Both list a 128K maximum output.", ["clm_fable_context", "clm_gpt_sol_context"], "context_tie", "THE SURPRISE", ["1M", "1.05M", "128K"], "proof", "remove the easy excuse"),
            ("tension", "BUT PRICE DOESN’T EQUAL TOTAL COST.", "Retries, latency, reliability, and completion rate belong in the production calculation.", ["clm_cost_interpretation"], "cost_iceberg", "THE CATCH", ["TOTAL COST"], "tension", "invite debate"),
            ("payoff", "TRACK COST PER SUCCESSFUL TASK.", "Token price starts the comparison. Your production outcomes should finish it.", ["clm_cost_interpretation"], "save_card", "THE METRIC", ["SUCCESSFUL TASK"], "payoff", "save + share"),
        ]
    elif "fable" in key:
        raw = [
            ("hook", "FABLE 5 VS GPT‑5.6 ISN’T A NORMAL MODEL FIGHT.", "One frontier bet versus a complete model system.", ["clm_fable_position", "clm_gpt_family"], "versus_cover", "FRONTIER MODELS", ["ISN’T", "MODEL FIGHT"], "open_loop", "swipe for the split"),
            ("lock_in", "FABLE 5 IS ONE FRONTIER BET.", "Anthropic built it for demanding reasoning and long-horizon agentic work.", ["clm_fable_position"], "single_frontier", "THE ANTHROPIC BET", ["ONE", "FRONTIER"], "reframe", "meet the specialist"),
            ("reveal", "GPT‑5.6 IS A THREE-TIER SYSTEM.", "Sol for frontier work. Terra for balance. Luna for high-volume efficiency.", ["clm_gpt_family"], "three_tiers", "THE OPENAI BET", ["THREE-TIER", "SYSTEM"], "contrast", "see the architecture"),
            ("mechanism", "THEIR CONTEXT WINDOWS ALMOST TIE.", "Fable lists 1M; Sol lists 1.05M. Both top out at 128K output.", ["clm_fable_context", "clm_gpt_sol_context"], "context_tie", "THE DRAW", ["1M", "1.05M", "128K"], "proof", "break the assumption"),
            ("proof", "THE PRICE TAGS DO NOT.", "Fable lists at $10/$50. Sol lists at $5/$30 per million input/output tokens.", ["clm_fable_price", "clm_gpt_sol_price"], "price_split", "THE RECEIPT", ["$10/$50", "$5/$30"], "proof", "show the bill"),
            ("tension", "THE CONTROL PHILOSOPHY SPLITS.", "Fable uses always-on adaptive thinking. GPT‑5.6 exposes effort from none through max.", ["clm_fable_adaptive", "clm_gpt_effort"], "control_split", "THE REAL DIFFERENCE", ["ALWAYS-ON", "NONE", "MAX"], "tension", "pick a philosophy"),
            ("payoff", "DON’T PICK THE “WINNER.” PICK THE SYSTEM.", "Choose the operating model that fits your workload, controls, and economics.", ["clm_comparison_interpretation"], "save_card", "THE MODEL PICKER", ["SYSTEM"], "payoff", "save + comment"),
        ]
    elif any(word in key for word in ("capability", "control", "safety", "cyber", "bio")):
        raw = [
            ("hook", "GPT‑5.6 BLOCKS ~10× MORE. HERE’S THE TRADEOFF.", "Stronger safeguards can also create friction for benign users.", ["clm_ten_times", "clm_benign_friction"], "cover_hero", "AI SAFETY", ["10×", "TRADEOFF"], "open_loop", "swipe for why"),
            ("lock_in", "WHY? OPENAI RATES ALL THREE “HIGH.”", "Sol, Terra, and Luna are treated as High in bio/chemical risk and cybersecurity.", ["clm_high_designation"], "risk_signal", "THE REFRAME", ["HIGH"], "reframe", "resolve the label"),
            ("reveal", "HIGH DOESN’T MEAN CRITICAL.", "OpenAI says none of the three crosses the Critical threshold.", ["clm_below_critical"], "threshold_split", "THE DISTINCTION", ["HIGH", "CRITICAL"], "contrast", "correct a misconception"),
            ("mechanism", "THE SAFETY STACK HAS FOUR LAYERS.", "Model protections → real-time checks → monitoring → account enforcement.", ["clm_layered_safeguards"], "system_layers", "HOW IT WORKS", ["FOUR LAYERS"], "mechanism", "earn a save"),
            ("proof", "MORE BLOCKING CAN MEAN MORE FRICTION.", "OpenAI explicitly acknowledges the cost for benign users.", ["clm_ten_times", "clm_benign_friction"], "proof_receipt", "THE RECEIPT", ["MORE FRICTION"], "proof", "show the source"),
            ("tension", "THE GOAL ISN’T “BLOCK EVERYTHING.”", "The stated aim is to stop serious misuse while preserving defensive work.", ["clm_controls_interpretation"], "tension_scale", "THE DESIGN BET", ["ISN’T"], "tension", "invite a side"),
            ("payoff", "CAPABILITY UP. CONTROLS UP. FRICTION UP.", "Would you accept more friction for stronger safeguards?", ["clm_controls_interpretation", "clm_benign_friction"], "save_card", "THE REAL STORY", ["CAPABILITY", "CONTROLS", "FRICTION"], "payoff", "save + comment"),
        ]
    else:
        raw = [
            ("hook", "GPT‑5.6 ISN’T ONE MODEL. IT’S THREE.", "Sol. Terra. Luna. Swipe for the difference.", ["clm_family_three"], "cover_hero", "NEW MODEL FAMILY", ["ISN’T", "THREE"], "open_loop", "swipe to decode"),
            ("lock_in", "YOU’RE PROBABLY STILL THINKING “ONE FLAGSHIP.”", "OpenAI now describes durable tiers that can advance on different cadences.", ["clm_family_interpretation"], "mental_model", "THE REFRAME", ["ONE FLAGSHIP"], "reframe", "break the old model"),
            ("reveal", "SOL = MAXIMUM CAPABILITY.", "The flagship tier for complex reasoning and coding.", ["clm_tier_roles"], "tier_sol", "TIER 01", ["SOL", "MAXIMUM"], "reveal", "meet the flagship"),
            ("reveal", "TERRA = THE BALANCE.", "The tier built to balance intelligence and cost.", ["clm_tier_roles"], "tier_terra", "TIER 02", ["TERRA", "BALANCE"], "reveal", "compare the middle"),
            ("reveal", "LUNA = SPEED + VOLUME.", "The cost-sensitive tier for high-volume workloads.", ["clm_tier_roles"], "tier_luna", "TIER 03", ["LUNA", "VOLUME"], "reveal", "complete the trio"),
            ("proof", "SAME FAMILY. DIFFERENT ACCESS.", "Availability spans ChatGPT, Codex, and API—but exact options depend on product and plan.", ["clm_available_surfaces", "clm_plan_qualified"], "proof_receipt", "THE FINE PRINT", ["DIFFERENT ACCESS"], "qualification", "show the receipt"),
            ("payoff", "SAVE THIS MODEL PICKER.", "Sol for hardest work. Terra for balance. Luna for scale.", ["clm_tier_roles"], "save_card", "THE TAKEAWAY", ["SOL", "TERRA", "LUNA"], "payoff", "save + share"),
        ]
    slides: List[SlideSpec] = []
    for index, item in enumerate(raw, start=1):
        role, headline, body, claim_ids, visual, eyebrow, accents, transition, trigger = item
        if all(claim_id in by_id for claim_id in claim_ids):
            slides.append(
                _slide(
                    index,
                    role,
                    headline,
                    body,
                    claim_ids,
                    claims,
                    visual,
                    eyebrow,
                    accents,
                    transition,
                    trigger,
                )
            )
    return slides


def _fit_story_count(base: Sequence[SlideSpec], count: int, claims: Sequence[Claim]) -> List[SlideSpec]:
    if count == 1:
        only = base[0]
        only.id = "slide_01"
        return [only]
    if count <= len(base):
        selected = list(base[: count - 1]) + [base[-1]]
    else:
        selected = list(base[:-1])
        while len(selected) < count - 1:
            claim = claims[len(selected) % len(claims)]
            selected.append(
                _slide(
                    len(selected) + 1,
                    "proof",
                    _words(claim.text.upper(), 11),
                    _words(claim.evidence_excerpt, 18),
                    [claim.id],
                    claims,
                    "proof_receipt",
                    "SOURCE CHECK",
                    [],
                    "proof",
                    "keep swiping",
                )
            )
        selected.append(base[-1])
    for index, slide in enumerate(selected, start=1):
        slide.id = f"slide_{index:02d}"
    return selected


def _generic_story(topic: str, claims: Sequence[Claim], count: int, hook: Dict[str, Any]) -> List[SlideSpec]:
    roles = ["hook", "lock_in", "reveal", "mechanism", "proof", "tension", "payoff"]
    visuals = ["cover_hero", "mental_model", "detail_crop", "system_layers", "proof_receipt", "tension_scale", "save_card"]
    slides: List[SlideSpec] = []
    for index in range(count):
        claim = claims[index % len(claims)]
        role = roles[min(index, len(roles) - 1)] if index < count - 1 else "payoff"
        headline = hook["text"] if index == 0 else _words(claim.text, 11)
        body = "SWIPE FOR THE SOURCE-BACKED MECHANISM." if index == 0 else _words(claim.evidence_excerpt, 20)
        if headline.rstrip(".…").lower() == body.rstrip(".…").lower():
            body = {
                "lock_in": "THIS IS THE PART THE HEADLINE LEAVES OUT.",
                "reveal": "ONE CLAIM. ONE VISUAL. KEEP SWIPING FOR THE MECHANISM.",
                "mechanism": "THE SOURCE CONNECTS THE CLAIM TO THE UNDERLYING MECHANISM.",
                "proof": "THE RECEIPT IS ATTACHED TO THIS CLAIM.",
                "tension": "THE IMPORTANT QUESTION IS WHAT THIS CHANGES IN PRACTICE.",
            }.get(role, "THE SOURCE-BACKED DETAIL IS SAVED WITH THIS DECK.")
        if role == "payoff":
            body = "SAVE THIS BREAKDOWN—THEN SEND IT TO SOMEONE WHO NEEDS THE SHORT VERSION."
        slides.append(
            _slide(
                index + 1,
                role,
                headline,
                body,
                hook["claim_ids"] if index == 0 else [claim.id],
                claims,
                visuals[min(index, len(visuals) - 1)],
                "SOURCE-BACKED BRIEF" if index == 0 else role.replace("_", " ").upper(),
                [],
                role,
                "save + share" if role == "payoff" else "swipe",
            )
        )
    return slides


def _primitive_for(claim: Claim, index: int) -> str:
    text = claim.text.lower()
    if re.search(
        r"\b(?:orbit(?:s|ed|ing)?|satellites?|gravity|planets?)\b|\borbital\s+(?:path|trajectory|mechanics?)\b",
        text,
    ):
        return "orbit_trace"
    if re.search(r"\b(?:gradients?|loss|slope|optimization|minimum|minima|learning rate)\b", text):
        return "gradient_descent"
    if re.search(r"\b(?:attention|queries|query|keys?|context|tokens?|softmax|values?)\b", text):
        return "attention_flow"
    if any(word in text for word in ("sol", "terra", "luna", "tier", "model")):
        return "model_cards" if index % 2 == 0 else "comparison_grid"
    if any(word in text for word in ("price", "token", "context", "cost")):
        return "tokens_context"
    if any(word in text for word in ("evaluation", "score", "times", "%")):
        return "eval_bars"
    if any(word in text for word in ("layer", "monitor", "safeguard", "control")):
        return "agent_loop"
    if any(word in text for word in ("available", "access", "plan", "api")):
        return "routing_diagram"
    if claim.claim_type == ClaimType.INTERPRETATION:
        return "before_after"
    return PRIMITIVES[index % len(PRIMITIVES)]


def _educational_headline(claim: Claim, index: int, hook: str, primitive: str) -> str:
    if index == 0:
        return _words(hook, 7)
    domain_headlines = {
        "orbit_trace": [
            "",
            "Add sideways velocity",
            "Gravity bends the path",
            "Speed sets the trajectory",
            "Orbits need no constant thrust",
        ],
        "gradient_descent": [
            "",
            "The gradient points uphill",
            "Recalculate after every step",
            "The learning rate sets step size",
            "Repeat toward lower loss",
        ],
        "attention_flow": [
            "",
            "Queries score the keys",
            "Softmax turns scores into weights",
            "Weighted values carry context",
            "Heads learn different relationships",
        ],
    }
    options = domain_headlines.get(primitive, [])
    if index < len(options) and options[index]:
        return options[index]
    return _words(claim.text, 7)


def _blocked_plan(topic: str, format_name: str, hook_style: str, reason: str) -> ContentPlan:
    return ContentPlan(
        id="plan_" + digest_text(topic + format_name)[:10],
        topic=topic,
        format=format_name,
        hook_style=hook_style,
        hook="",
        visual_thesis="No render: source grounding is incomplete.",
        source_ids=[],
        claims=[],
        grounded=False,
        blocked_reason=reason,
    )


def _placeholder_claim(topic: str) -> Claim:
    return Claim(
        id="clm_ungrounded",
        text=f"Ungrounded placeholder about {topic}.",
        evidence_excerpt="No source supplied; explicitly requested placeholder.",
        source_id="ungrounded",
        source_url="",
        source_label="UNGROUNDED",
        confidence=0.0,
        claim_type=ClaimType.SPECULATION,
    )


def plan_video(
    topic: str,
    sources: List[SourceArtifact],
    claims: List[Claim],
    hook_style: str = "direct",
    allow_ungrounded: bool = False,
) -> ContentPlan:
    if not sources or not claims:
        reason = "No sufficient source-backed claims were found. Add --source-url or --source-file."
        if not allow_ungrounded:
            return _blocked_plan(topic, "video", hook_style, reason)
        claims = [_placeholder_claim(topic)]
    hook = _hook(topic, hook_style, claims)
    selected = _ordered_for_hook(hook_style, claims)[:5]
    beats: List[VideoBeat] = []
    middle_purposes = ["setup", "mechanism", "proof", "qualification"]
    purposes = ["hook"] + middle_purposes[: max(0, len(selected) - 2)] + (["payoff"] if len(selected) > 1 else [])
    for index, claim in enumerate(selected):
        primitive = _primitive_for(claim, index)
        headline = _educational_headline(claim, index, hook, primitive)
        if index == 0:
            hook_sentence = hook.rstrip(".?!") + ("?" if hook_style == "question" else ".")
            narration = claim.text if hook_sentence.rstrip(".") == claim.text.rstrip(".") else f"{hook_sentence} {claim.text}"
        else:
            narration = claim.text
        beats.append(
            VideoBeat(
                id=f"beat_{index + 1:02d}",
                purpose=purposes[min(index, len(purposes) - 1)],
                headline=headline,
                narration=narration,
                on_screen_text=_words(claim.text, 7),
                claim_ids=[claim.id],
                source_label=claim.source_label,
                primitive=primitive,
                duration_seconds=3.0 if index else 2.5,
            )
        )
    if len(beats) == 1:
        beats.append(
            VideoBeat(
                id="beat_02",
                purpose="takeaway",
                headline="Verify the source before publishing.",
                narration=claims[0].text,
                on_screen_text=claims[0].text,
                claim_ids=[claims[0].id],
                source_label=claims[0].source_label,
                primitive="claim_callout",
                duration_seconds=3.0,
            )
        )
    return ContentPlan(
        id="plan_" + digest_text(topic + "video" + hook_style)[:10],
        topic=topic,
        format="video",
        hook_style=hook_style,
        hook=hook,
        visual_thesis="Build one persistent explanatory diagram, transform it with each cited claim, and finish on the narrow sourced takeaway.",
        source_ids=[source.id for source in sources],
        claims=claims,
        beats=beats,
        grounded=bool(sources),
        blocked_reason=None if sources else "Explicitly allowed ungrounded placeholder.",
    )


def plan_slides(
    topic: str,
    sources: List[SourceArtifact],
    claims: List[Claim],
    count: int,
    hook_style: str = "direct",
    allow_ungrounded: bool = False,
    visual_theme: str = "editorial_heat_v1",
) -> ContentPlan:
    if count < 1:
        raise PlanningError("--count must be at least 1")
    if not sources or not claims:
        reason = "No sufficient source-backed claims were found. Add --source-url or --source-file."
        if not allow_ungrounded:
            return _blocked_plan(topic, "carousel", hook_style, reason)
        claims = [_placeholder_claim(topic)]
    if hook_style == "statistic" and not any(claim.numeric for claim in claims):
        raise PlanningError("statistic hooks require a numeric source-backed claim")
    candidates = _hook_candidates(topic, claims)
    selected_hook = _pick_hook(hook_style, candidates)
    packed_story = _gpt56_story(topic, claims) if editorial_title(topic) or "fable" in topic.lower() else []
    slides = _fit_story_count(packed_story, count, claims) if packed_story else _generic_story(topic, claims, count, selected_hook)
    if slides:
        slides[0].headline = selected_hook["text"]
        slides[0].claim_ids = list(selected_hook["claim_ids"])
        slides[0].source_label = _claim_lookup(claims)[slides[0].claim_ids[0]].source_label
    return ContentPlan(
        id="plan_" + digest_text(topic + "carousel" + hook_style + str(count))[:10],
        topic=topic,
        format="carousel",
        hook_style=hook_style,
        hook=selected_hook["text"],
        visual_thesis=(
            "A tactile paper-and-meme collage opens a curiosity gap; doodles, receipts, and reaction panels make each swipe feel authored and native."
            if visual_theme == "paper_meme_v1"
            else "A cinematic editorial cover opens a curiosity gap; each swipe delivers one reveal, receipt, or tension point before a save-worthy payoff."
        ),
        source_ids=[source.id for source in sources],
        claims=claims,
        slides=slides,
        grounded=bool(sources),
        blocked_reason=None if sources else "Explicitly allowed ungrounded placeholder.",
        narrative_pattern="cover_lock-in_reveal_mechanism_proof_tension_payoff",
        engagement_goal="maximize swipe depth, saves, sends, and follow conversion without weakening source grounding",
        hook_candidates=candidates,
        angle_candidates=_angle_candidates(topic),
        publishing_notes=[
            "A/B test the three rendered cover variants before publishing.",
            "Add relevant platform-native music when posting the Instagram carousel.",
            "Judge the post by swipe depth, sends, saves, and follow conversion—not likes alone.",
            "Turn the winning cover and narrative into a Photo Mode post and a short-form video cut.",
        ],
        visual_theme=visual_theme,
    )


def write_citations(job_dir: Path, plans: Iterable[ContentPlan]) -> Path:
    claims = {}
    for plan in plans:
        for claim in plan.claims:
            claims[claim.id] = claim
    lines = ["# Citations", ""]
    for claim in sorted(claims.values(), key=lambda item: item.id):
        label = claim.source_label or "Unlabeled source"
        source = f"[{label}]({claim.source_url})" if claim.source_url else label
        lines.extend(
            [
                f"## {claim.id}",
                "",
                claim.text,
                "",
                f"- Type: `{claim.claim_type.value}`",
                f"- Confidence: `{claim.confidence:.2f}`",
                f"- Source: {source}",
                f"- Evidence: {claim.evidence_excerpt}",
                "",
            ]
        )
    path = job_dir / "citations.md"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
