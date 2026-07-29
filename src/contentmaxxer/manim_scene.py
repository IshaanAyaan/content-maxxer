"""Compile source-grounded video plans into deterministic Manim scenes."""

import importlib.util
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .io import write_json
from .models import ContentPlan, ManimPrimitiveSpec, ManimSceneSpec, NarrationCue, NarrationTrack


SAFE_ZONE = {"top": 170, "right": 90, "bottom": 310, "left": 90}
CAPTION_RAIL = {"top": 1440, "bottom": 1600, "left": 90, "right": 990}
ANIMATION_STYLES = (
    "hand_drawn",
    "whiteboard",
    "warm_papyrus",
    "future_minimal",
    "director_cut",
)
STYLE_BACKGROUNDS = {
    "hand_drawn": "#07111F",
    "whiteboard": "#F7F3E8",
    "warm_papyrus": "#E7D1A5",
    "future_minimal": "#050914",
    "director_cut": "#111018",
}

SEMANTIC_TRIGGER_PHRASES = {
    "elastic_llm_nesting": (
        "google", "model", "smaller", "hiding", "inside", "matformer",
        "matryoshka", "doll*", "gemma", "e4b", "e2b", "trains", "optimized",
        "same time", "size", "between", "mix-n-match", "mix n match",
        "slices", "custom", "resizing", "layer*", "feed-forward", "skipping",
        "no retraining", "nvidia", "flextron", "converts", "existing",
        "eight percent", "training tokens", "train once", "family",
        "sliced", "prove", "separately trained",
    ),
    "lecun_world_model_bet": (
        "yann lecun", "one point oh three", "billion", "bet", "llm-only",
        "ami", "world model*", "predict*", "next word", "what happens next",
        "video", "sensor*", "action*", "real intelligence", "world",
        "language", "prove",
    ),
    "technology_adolescence": (
        "adolescence", "humanity", "enormous power", "maturity", "amodei",
        "country of geniuses", "datacenter", "millions", "faster", "autonomy",
        "destructive", "political power", "economic disruption", "panic",
        "denial", "uncertainty", "evidence", "defenses", "surgically",
        "rite of passage", "grow up", "guide",
    ),
    "open_weights_debate": (
        "nvidia", "amodei", "opposed", "they arent", "real fight", "frontier risk",
        "versus closed", "weights", "access", "competition", "control", "customers",
        "downloadable", "released", "pull them back", "withdraw", "no undo", "catch",
        "transparency", "inspect", "strengthen", "defender*", "attacker*", "gains more",
        "ban", "instead", "restrict*", "chip*", "distill*", "test capable", "open and closed",
    ),
    "mechanism_bayes": (
        "fair", "trick", "heads", "coin", "which", "prior", "odds", "fifty",
        "likelihood", "predicted", "weight*", "posterior", "reweight*",
    ),
    "mechanism_orbit": (
        "earth", "satellite", "gravity", "pull", "fall", "down", "sideways",
        "velocity", "speed", "orbit", "curve", "path", "trajectory", "thrust",
    ),
    "mechanism_gradient": (
        "loss", "curve", "gradient", "uphill", "slope", "opposite", "step",
        "recalculate", "repeat", "update*", "learning rate", "overshoot", "minimum",
        "lower", "model", "current",
    ),
    "mechanism_attention": (
        "token*", "query", "key*", "score*", "softmax", "weight*", "value*",
        "context", "combine*", "weighted", "head*", "parallel", "relationship*",
    ),
    "mechanism_handshake": (
        "tls", "client", "clienthello", "client hello", "server", "serverhello",
        "server hello", "offer*", "supported", "protocol", "parameters", "includes",
        "key share", "share", "establish*", "keying", "keys", "exchanged",
        "peer*", "derive", "same", "secret*", "network", "send*",
        "message*", "select*", "encrypted", "certificate", "certificateverify",
        "certificate verify", "signature",
        "authenticate*", "finished", "transcript", "computed keys", "incorrect",
        "correct", "terminate", "connection", "both sides", "established",
        "application data", "traffic keys", "protect*",
    ),
}

GENERIC_TRIGGER_STOPWORDS = {
    "a",
    "after",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "both",
    "before",
    "but",
    "by",
    "can",
    "each",
    "first",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "once",
    "or",
    "that",
    "the",
    "their",
    "then",
    "these",
    "they",
    "this",
    "to",
    "use",
    "with",
}


def _semantic_trigger_word_index(words: List[object], story_kind: str) -> Optional[int]:
    normalized = [re.sub(r"[^a-z0-9]+", "", str(word.text).lower()) for word in words]
    for index in range(len(normalized)):
        for phrase in SEMANTIC_TRIGGER_PHRASES.get(story_kind, ()):
            parts = phrase.split()
            if index + len(parts) > len(normalized):
                continue
            matched = True
            for offset, part in enumerate(parts):
                candidate = normalized[index + offset]
                if part.endswith("*"):
                    matched = candidate.startswith(part[:-1])
                else:
                    matched = candidate == re.sub(r"[^a-z0-9]+", "", part)
                if not matched:
                    break
            if matched:
                return index
    if story_kind == "causal_explainer":
        for index, candidate in enumerate(normalized):
            if (
                candidate
                and candidate not in GENERIC_TRIGGER_STOPWORDS
                and not candidate.isdigit()
                and len(candidate) >= 3
            ):
                return index
    return None


def _visual_label(value: str, limit: int = 4) -> str:
    compact = " ".join(value.replace("‑", "-").split()).strip(" .?!")
    compact = re.sub(
        r"^(?:why|how|what)\s+(?:(?:do|does|did|can|is|are|will)\s+)?",
        "",
        compact,
        flags=re.I,
    )
    words = compact.split()
    return " ".join(words[:limit]).rstrip(".,;:") + ("…" if len(words) > limit else "")


def _persistent_hook_title(plan: ContentPlan) -> Dict[str, object]:
    planned = " ".join(plan.hook.replace("‑", "-").split()).strip()
    first_headline = (
        " ".join(plan.beats[0].headline.replace("‑", "-").split()).strip()
        if plan.beats
        else ""
    )
    has_truncation = "…" in first_headline or "..." in first_headline
    if plan.hook_style == "question" and planned:
        title = planned
        source = "exact_plan_question"
    elif first_headline and not has_truncation:
        title = first_headline
        source = "intentional_editorial_headline"
    else:
        topic = " ".join(plan.topic.replace("‑", "-").split()).strip(" .?!")
        if plan.hook_style == "curiosity":
            if topic.casefold().endswith("handshake"):
                article = (
                    ""
                    if topic.casefold().startswith(("a ", "an ", "the "))
                    else "a "
                )
                title = f"What happens during {article}{topic}?"
            else:
                title = f"What happens inside {topic}?"
            source = "topic_bound_curiosity_question"
        else:
            title = topic
            source = "complete_topic_title"
    title = title.replace("…", "").replace("...", "").strip()
    if plan.hook_style == "question" and title and not title.endswith("?"):
        title += "?"
    return {
        "text": title,
        "source": source,
        "matches_plan_hook": (
            plan.hook_style != "question"
            or title.casefold() == planned.casefold()
        ),
        "contains_ellipsis": "…" in title or "..." in title,
        "word_count": len(title.split()),
    }


def _is_causal_sequence(plan: ContentPlan) -> bool:
    if len(plan.beats) < 4:
        return False
    sequence_pattern = re.compile(
        r"\b(?:first|start(?:s|ed|ing)?|begin(?:s|ning)?|then|next|after|"
        r"before|once|finally|respond(?:s|ed)?|answer(?:s|ed)?|"
        r"repeat(?:s|ed|ing)?|return(?:s|ed|ing)?)\b",
        re.I,
    )
    mechanism_pattern = re.compile(
        r"\b(?:cause(?:s|d)?|allow(?:s|ed)?|enable(?:s|d)?|derive(?:s|d)?|"
        r"send(?:s|ing)?|convert(?:s|ed)?|transform(?:s|ed)?|produce(?:s|d)?|"
        r"transfer(?:s|red|ring)?|enter(?:s|ed|ing)?|absorb(?:s|ed|ing)?|"
        r"evaporat(?:e|es|ed|ing)|boil(?:s|ed|ing)?|compress(?:es|ed|ing)?|"
        r"squeez(?:e|es|ed|ing)|rais(?:e|es|ed|ing)|releas(?:e|es|ed|ing)|"
        r"condens(?:e|es|ed|ing)|reduc(?:e|es|ed|ing)|expand(?:s|ed|ing)?|"
        r"return(?:s|ed|ing)?|repeat(?:s|ed|ing)?|"
        r"protect(?:s|ed)?|move(?:s|d)?|flow(?:s|ed)?|verify|validate|"
        r"authenticate(?:s|d)?|compute(?:s|d)?)\b",
        re.I,
    )
    claim_texts = [claim.text for claim in plan.claims]
    causal_claim_count = sum(
        bool(sequence_pattern.search(text) or mechanism_pattern.search(text))
        for text in claim_texts
    )
    has_explicit_order = any(sequence_pattern.search(text) for text in claim_texts)
    return causal_claim_count >= 3 and has_explicit_order


def _causal_step_label(
    plan: ContentPlan,
    beat: object,
    *,
    concise: bool = True,
) -> str:
    claim_by_id = {claim.id: claim for claim in plan.claims}
    source_text = " ".join(
        claim_by_id[claim_id].text
        for claim_id in beat.claim_ids
        if claim_id in claim_by_id
    ) or beat.on_screen_text
    compact = " ".join(source_text.replace("‑", "-").split()).strip(" .?!")
    compact = re.sub(
        r"^(?:first|then|next|finally|after that|at this point)\b[\s,:-]*",
        "",
        compact,
        flags=re.I,
    )
    contextual_prefix = re.match(
        r"^(?:in|after|before|when|once|during|at|if|as|while)\b[^,]{0,100},\s*(.+)$",
        compact,
        re.I,
    )
    if contextual_prefix:
        compact = contextual_prefix.group(1)
    if not concise:
        return _visual_label(compact, 7)
    return _concise_process_label(
        compact,
        " ".join(source_text.replace("‑", "-").split()).strip(" .?!"),
    )


PROCESS_LABEL_ACTIONS = (
    ("request", r"\brequest(?:s|ed|ing)?\b"),
    ("check", r"\bcheck(?:s|ed|ing)?\b"),
    ("find", r"\bfind(?:s|ing)?\b"),
    ("transfer", r"\btransfer(?:s|red|ring)?\b"),
    ("absorb", r"\babsorb(?:s|ed|ing)?\b"),
    ("boil", r"\bboil(?:s|ed|ing)?\b"),
    ("compress", r"\b(?:compress|squeez)(?:e|es|ed|ing)?\b"),
    ("release", r"\breleas(?:e|es|ed|ing)\b"),
    ("condense", r"\bcondens(?:e|es|ed|ing)\b"),
    ("limit", r"\blimit(?:s|ed|ing)?\b"),
    ("probe", r"\bprob(?:e|es|ed|ing)\b"),
    ("increase", r"\b(?:increase|increment|grow|raise)(?:s|d|ing)?\b"),
    ("moderate", r"\b(?:moderate|slow)(?:s|d|ing)?\b"),
    ("detect", r"\bdetect(?:s|ed|ing)?\b"),
    ("reduce", r"\b(?:reduce|decrease|lower|halve|cut)(?:s|d|ing)?\b"),
    ("verify", r"\bverif(?:y|ies|ied|ying)\b"),
    ("establish", r"\bestablish(?:es|ed|ing)?\b"),
    ("send", r"\bsend(?:s|ing)?\b"),
    ("point", r"\bpoint(?:s|ed|ing)?\b"),
    ("update", r"\bupdate(?:s|d|ing)?\b"),
    ("repeat", r"\brepeat(?:s|ed|ing)?\b"),
    ("return", r"\breturn(?:s|ed|ing)?\b"),
    ("store", r"\bstore(?:s|d|ing)?\b"),
    ("tokenize", r"\btokeniz(?:e|es|ed|ing)\b"),
    ("build", r"\bbuild(?:s|ing)?\b"),
    ("combine", r"\bcombin(?:e|es|ed|ing)\b"),
    ("compute", r"\bcomput(?:e|es|ed|ing)\b"),
    ("paint", r"\bpaint(?:s|ed|ing)?\b"),
    ("derive", r"\bderive(?:s|d|ing)?\b"),
    ("convert", r"\bconvert(?:s|ed|ing)?\b"),
    ("transform", r"\btransform(?:s|ed|ing)?\b"),
    ("protect", r"\bprotect(?:s|ed|ing)?\b"),
    ("receive", r"\breceive(?:s|d|ing)?\b"),
)
PROCESS_LABEL_FILLERS = {
    "a",
    "an",
    "the",
    "its",
    "their",
    "this",
    "that",
    "initial",
    "resulting",
    "available",
    "associated",
    "requested",
    "usable",
    "locally",
    "finally",
    "next",
    "then",
    "first",
}
PROCESS_LABEL_TOKEN_STOPWORDS = PROCESS_LABEL_FILLERS | {
    "and",
    "or",
    "but",
    "to",
    "for",
    "of",
    "in",
    "into",
    "through",
    "toward",
    "while",
    "when",
    "once",
    "after",
    "before",
    "by",
    "from",
    "with",
    "more",
    "one",
}


def _concise_process_label(compact: str, source_text: str) -> str:
    searchable = source_text.casefold()
    source_rules = (
        (
            all(term in searchable for term in ("requests a page", "ip address", "dns")),
            "request page • find server IP",
        ),
        (
            all(term in searchable for term in ("tls", "verif", "https", "secure connection")),
            "verify HTTPS server • establish secure connection",
        ),
        (
            "http get request" in searchable,
            "send HTTP GET request",
        ),
        (
            "tokeniz" in searchable and "dom tree" in searchable,
            "tokenize HTML • build DOM",
        ),
        (
            all(term in searchable for term in ("dom", "cssom", "paint")),
            "combine DOM + CSSOM • paint pixels",
        ),
        (
            "cached records" in searchable and "local" in searchable,
            "check local cache",
        ),
        (
            "dns query" in searchable,
            "send DNS query",
        ),
        (
            "referral" in searchable and "closer name server" in searchable,
            "referral points to closer server",
        ),
        (
            "authoritative answer" in searchable and "address" in searchable,
            "return authoritative address",
        ),
        (
            "time to live" in searchable and "store" in searchable,
            "return answer • store by time to live",
        ),
        (
            "congestion window" in searchable
            and "probe" in searchable
            and "capacity" in searchable,
            "limit in-flight data • probe capacity",
        ),
        (
            "ack" in searchable
            and ("increment" in searchable or "increase" in searchable)
            and ("cwnd" in searchable or "window" in searchable),
            "ACK increases window",
        ),
        (
            "slow-start threshold" in searchable
            and ("gradually" in searchable or "more slowly" in searchable),
            "cross threshold • grow window gradually",
        ),
        (
            "loss" in searchable
            and "reduce" in searchable
            and ("cwnd" in searchable or "congestion window" in searchable),
            "detect loss • reduce window",
        ),
        (
            "feedback loop" in searchable
            and "ack" in searchable
            and ("congestion lowers" in searchable or "loss lowers" in searchable),
            "ACKs raise window • congestion lowers it",
        ),
    )
    for matched, label in source_rules:
        if matched:
            return label

    action_matches = []
    for canonical, pattern in PROCESS_LABEL_ACTIONS:
        for match in re.finditer(pattern, compact, re.I):
            action_matches.append((match.start(), match.end(), canonical))
    action_matches.sort(key=lambda item: item[0])
    phrases: List[str] = []
    used_words = 0
    for match_index, (start, end, canonical) in enumerate(action_matches):
        next_start = (
            action_matches[match_index + 1][0]
            if match_index + 1 < len(action_matches)
            else len(compact)
        )
        tail = compact[end:next_start]
        tail = re.split(r"[,;:.]|\b(?:and|but|so|while)\b", tail, maxsplit=1, flags=re.I)[0]
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'+.-]*", tail)
        content = [
            token
            for token in tokens
            if token.casefold() not in PROCESS_LABEL_FILLERS
        ][:3]
        phrase_words = [canonical] + content
        if used_words + len(phrase_words) > 8:
            available = 8 - used_words
            phrase_words = phrase_words[:available]
        if not phrase_words:
            continue
        phrases.append(" ".join(phrase_words))
        used_words += len(phrase_words)
        if used_words >= 8 or len(phrases) >= 3:
            break
    if phrases:
        return " • ".join(phrases)
    fallback_tokens = [
        token
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'+.-]*", compact)
        if token.casefold() not in PROCESS_LABEL_TOKEN_STOPWORDS
    ]
    return " ".join(fallback_tokens[:8]) or "next sourced step"


def _label_source_token_overlap(label: str, source_text: str) -> int:
    def stem(token: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "", token.casefold())
        for suffix in ("ing", "ied", "ed", "es", "s"):
            if len(value) >= len(suffix) + 4 and value.endswith(suffix):
                value = value[: -len(suffix)]
                break
        return value

    label_tokens = {
        stem(token)
        for token in label.split()
        if token.casefold() not in PROCESS_LABEL_TOKEN_STOPWORDS
        and stem(token)
    }
    source_tokens = {
        stem(token)
        for token in source_text.split()
        if stem(token)
    }
    return sum(
        any(
            label_token == source_token
            or (
                min(len(label_token), len(source_token)) >= 4
                and (
                    label_token.startswith(source_token)
                    or source_token.startswith(label_token)
                )
            )
            for source_token in source_tokens
        )
        for label_token in label_tokens
    )


def _process_role(plan: ContentPlan, beat: object, index: int) -> str:
    """Classify a grounded process step into a reusable visual operation."""
    claim_by_id = {claim.id: claim for claim in plan.claims}
    source_text = " ".join(
        claim_by_id[claim_id].text
        for claim_id in beat.claim_ids
        if claim_id in claim_by_id
    )
    searchable = f"{source_text} {beat.headline} {beat.on_screen_text}".lower()
    role_patterns = (
        ("FEEDBACK", r"\b(?:feedback loop|feeds? back|probe(?:s|d|ing)? again|repeat(?:s|ed|ing)? the (?:cycle|probe))\b"),
        ("RETURN", r"\b(?:return(?:s|ed|ing)? to|cycle repeat(?:s|ed|ing)?|repeat(?:s|ed|ing)? the cycle)\b"),
        ("ABSORB", r"\b(?:absorb(?:s|ed|ing)?|evaporat(?:e|es|ed|ing)|boil(?:s|ed|ing)?)\b"),
        ("COMPRESS", r"\b(?:compress(?:or|es|ed|ing)?|squeez(?:e|es|ed|ing))\b"),
        (
            "RELEASE",
            r"\b(?:releas(?:e|es|ed|ing) .{0,24}\bheat|"
            r"gives? up heat|condens(?:e|es|ed|ing))\b",
        ),
        ("EXPAND", r"\b(?:expansion valve|pressure drop|throttl(?:e|es|ed|ing))\b"),
        ("ADJUST", r"\b(?:reduce(?:s|d|ing)?|decrease(?:s|d|ing)?|lower(?:s|ed|ing)?|halve(?:s|d|ing)?|back(?:s|ed|ing)? off|adjust(?:s|ed|ing)?)\b"),
        ("MODERATE", r"\b(?:more gradually|more slowly|congestion avoidance|moderate(?:s|d|ing)?)\b"),
        ("EXPAND", r"\b(?:increase(?:s|d|ing)?|increment(?:s|ed|ing)?|grow(?:s|ing)?|raise(?:s|d|ing)?)\b"),
        ("PROBE", r"\b(?:probe(?:s|d|ing)?|slow start|unknown (?:network |path )?conditions|available capacity)\b"),
        ("STORE", r"\b(?:store(?:s|d|ing)?|persist(?:s|ed|ing)?|save(?:s|d|ing)?|retain(?:s|ed|ing)?)\b"),
        ("ROUTE", r"\b(?:referral|delegation|route(?:s|d|ing)?|closer server|next server|points? (?:it|the resolver))\b"),
        ("DISPATCH", r"\b(?:send(?:s|ing)?|quer(?:y|ies|ied|ying)|ask(?:s|ed|ing)?|offer(?:s|ed|ing)?)\b"),
        ("LOOKUP", r"\b(?:cache|cached|local information|look(?:s|ed|ing)? up|search(?:es|ed|ing)?|find(?:s|ing)?)\b"),
        ("VERIFY", r"\b(?:verif(?:y|ies|ied|ying)|validat(?:e|es|ed|ing)|authenticat(?:e|es|ed|ing)|check(?:s|ed|ing)?|match(?:es|ed|ing)?)\b"),
        ("TRANSFORM", r"\b(?:derive(?:s|d|ing)?|comput(?:e|es|ed|ing)|convert(?:s|ed|ing)?|transform(?:s|ed|ing)?|produc(?:e|es|ed|ing))\b"),
        ("RESOLVE", r"\b(?:return(?:s|ed|ing)?|answer(?:s|ed|ing)?|result|output|receive(?:s|d|ing)?|requested record|address)\b"),
    )
    for role, pattern in role_patterns:
        if re.search(pattern, searchable, re.I):
            return role
    if index == 0:
        return "INPUT"
    if index >= len(plan.beats) - 1:
        return "OUTPUT"
    return "TRANSFORM"


FEEDBACK_STATE_TOKENS = (
    "cwnd",
    "window",
    "rate",
    "capacity",
    "threshold",
    "level",
    "state",
    "budget",
    "pressure",
)


def _feedback_loop_contract(plan: ContentPlan) -> Dict[str, object]:
    """Detect an explicit source-backed grow/correct/repeat control loop."""
    claim_by_id = {claim.id: claim for claim in plan.claims}
    stage_texts = [
        " ".join(
            claim_by_id[claim_id].text
            for claim_id in beat.claim_ids
            if claim_id in claim_by_id
        ).casefold()
        for beat in plan.beats
    ]
    expansion_pattern = re.compile(
        r"\b(?:increase|increment|grow|raise|expand|probe)(?:s|d|ing)?\b",
        re.I,
    )
    correction_pattern = re.compile(
        r"\b(?:reduce|decrease|lower|halve|cut|back(?:s|ed|ing)? off|adjust)(?:s|d|ing)?\b",
        re.I,
    )
    recurrence_pattern = re.compile(
        r"\b(?:feedback loop|feeds? back|probe(?:s|d|ing)? again|"
        r"repeat(?:s|ed|ing)? (?:the )?(?:cycle|probe|process)|"
        r"new .{0,28} later .{0,28})\b",
        re.I,
    )
    expansion_indices = [
        index
        for index, text in enumerate(stage_texts)
        if expansion_pattern.search(text)
    ]
    correction_indices = [
        index
        for index, text in enumerate(stage_texts)
        if correction_pattern.search(text)
    ]
    recurrence_indices = [
        index
        for index, text in enumerate(stage_texts)
        if recurrence_pattern.search(text)
    ]
    expansion_text = " ".join(stage_texts[index] for index in expansion_indices)
    correction_text = " ".join(stage_texts[index] for index in correction_indices)
    shared_state_tokens = [
        token
        for token in FEEDBACK_STATE_TOKENS
        if token in expansion_text and token in correction_text
    ]
    evidence_indices = sorted(
        set(expansion_indices + correction_indices + recurrence_indices)
    )
    detected = (
        len(plan.beats) >= 4
        and bool(expansion_indices)
        and bool(correction_indices)
        and bool(recurrence_indices)
        and bool(shared_state_tokens)
        and max(correction_indices) > min(expansion_indices)
        and max(recurrence_indices) >= max(correction_indices)
        and len(evidence_indices) >= 3
    )
    return {
        "mode": (
            "source_feedback_loop_v1"
            if detected
            else "linear_process_v1"
        ),
        "detected": detected,
        "expansion_stage_indices": expansion_indices if detected else [],
        "correction_stage_indices": correction_indices if detected else [],
        "recurrence_stage_indices": recurrence_indices if detected else [],
        "return_from_stage_index": (
            max(recurrence_indices) if detected else None
        ),
        "return_to_stage_index": (
            max(0, min(expansion_indices) - 1) if detected else None
        ),
        "shared_state_tokens": shared_state_tokens if detected else [],
        "evidence_stage_count": len(evidence_indices) if detected else 0,
    }


CYCLE_STATE_TOKENS = (
    "refrigerant",
    "evaporator",
    "fluid",
    "vapor",
    "liquid",
    "gas",
    "water",
    "air",
    "dna",
    "material",
)


def _cycle_loop_contract(plan: ContentPlan) -> Dict[str, object]:
    """Detect an explicit source-backed material or state cycle."""
    claim_by_id = {claim.id: claim for claim in plan.claims}
    stage_texts = [
        " ".join(
            claim_by_id[claim_id].text
            for claim_id in beat.claim_ids
            if claim_id in claim_by_id
        ).casefold()
        for beat in plan.beats
    ]
    recurrence_pattern = re.compile(
        r"\b(?:cycle repeat(?:s|ed|ing)?|repeat(?:s|ed|ing)? "
        r"(?:the |this |same )?(?:cycle|process)|"
        r"return(?:s|ed|ing)? to .{0,60}(?:where|and|so|to) .{0,40}"
        r"(?:repeat|begin|start)|complet(?:e|es|ed|ing) the cycle)\b",
        re.I,
    )
    action_pattern = re.compile(
        r"\b(?:transfer|enter|absorb|evaporate|boil|compress|squeeze|"
        r"raise|release|condense|reduce|expand|return|flow|move)"
        r"(?:s|d|ed|ing)?\b",
        re.I,
    )
    recurrence_indices = [
        index
        for index, text in enumerate(stage_texts)
        if recurrence_pattern.search(text)
    ]
    action_indices = [
        index
        for index, text in enumerate(stage_texts)
        if action_pattern.search(text)
    ]
    recurrence_text = " ".join(
        stage_texts[index] for index in recurrence_indices
    )
    shared_state_tokens = [
        token
        for token in CYCLE_STATE_TOKENS
        if token in recurrence_text
        and any(
            token in text
            for index, text in enumerate(stage_texts)
            if index not in recurrence_indices
        )
    ]
    return_from = max(recurrence_indices) if recurrence_indices else None
    return_to_candidates = [
        index
        for index, text in enumerate(stage_texts)
        if (
            return_from is not None
            and index < return_from
            and any(token in text for token in shared_state_tokens)
        )
    ]
    return_to = (
        min(return_to_candidates)
        if return_to_candidates
        else None
    )
    evidence_indices = sorted(set(action_indices + recurrence_indices))
    detected = (
        len(plan.beats) >= 4
        and len(action_indices) >= 3
        and bool(recurrence_indices)
        and bool(shared_state_tokens)
        and isinstance(return_from, int)
        and isinstance(return_to, int)
        and return_from > return_to
        and len(evidence_indices) >= 4
    )
    return {
        "mode": "source_cycle_loop_v1" if detected else "linear_process_v1",
        "detected": detected,
        "action_stage_indices": action_indices if detected else [],
        "recurrence_stage_indices": recurrence_indices if detected else [],
        "return_from_stage_index": return_from if detected else None,
        "return_to_stage_index": return_to if detected else None,
        "shared_state_tokens": shared_state_tokens if detected else [],
        "evidence_stage_count": len(evidence_indices) if detected else 0,
    }


def _source_visual_profile(searchable: str) -> str:
    """Select a topic-specific visual grammar only from complete source evidence."""
    heat_pump_identity = "heat pump" in searchable
    heat_pump_evidence_groups = (
        ("refrigerant",),
        ("evaporator",),
        ("compressor",),
        ("condenser",),
        ("expansion valve",),
        ("absorbs heat", "absorb heat"),
        ("release heat", "gives up heat"),
        ("cycle repeats", "repeat the cycle"),
    )
    if heat_pump_identity and all(
        any(term in searchable for term in alternatives)
        for alternatives in heat_pump_evidence_groups
    ):
        return "heat_pump_cycle_v1"
    tcp_identity = (
        "tcp" in searchable
        or "transmission control protocol" in searchable
    )
    tcp_evidence_groups = (
        ("congestion window",),
        ("slow start", "slow-start"),
        ("acknowledgment", "acknowledgement", "ack"),
        ("congestion avoidance",),
        ("retransmission timeout",),
        ("threshold",),
        ("in-flight", "in flight"),
    )
    if tcp_identity and all(
        any(term in searchable for term in alternatives)
        for alternatives in tcp_evidence_groups
    ):
        return "tcp_congestion_control_v1"
    return "generic_process_v1"


def _visual_story(plan: ContentPlan) -> Dict[str, object]:
    searchable = " ".join([plan.topic] + [claim.text for claim in plan.claims]).lower()
    elastic_llm_groups = (
        ("matformer",),
        ("matryoshka",),
        ("e2b",),
        ("e4b",),
        ("mix-n-match", "mix n match"),
        ("flextron",),
        ("7.63",),
        ("elastic",),
        ("nested", "nests"),
        ("without any retraining", "no additional fine-tuning"),
        ("have to prove", "has to prove"),
    )
    elastic_llm_nesting = all(
        any(term in searchable for term in alternatives)
        for alternatives in elastic_llm_groups
    )
    lecun_world_model_groups = (
        ("yann lecun",),
        ("advanced machine intelligence", "ami labs"),
        ("1.03 billion",),
        ("next-token", "predicting tokens"),
        ("sensor data",),
        ("video",),
        ("consequences of actions",),
        ("plan", "planning"),
        ("real intelligence",),
        ("starts in the world",),
        ("have to prove", "not a demonstrated victory"),
    )
    lecun_world_model_bet = all(
        any(term in searchable for term in alternatives)
        for alternatives in lecun_world_model_groups
    )
    technology_adolescence_groups = (
        ("rite of passage", "technological adolescence"),
        ("enormous power", "immense power"),
        ("mature enough", "maturity"),
        ("country of geniuses in a datacenter",),
        ("autonomous", "human intentions"),
        ("destructive misuse", "biological"),
        ("political power", "seize", "entrench"),
        ("economic disruption",),
        ("doomerism",),
        ("uncertainty",),
        ("evidence",),
        ("defenses",),
        ("surgical", "targeted"),
        ("beneficial", "steering", "survive"),
    )
    technology_adolescence = (
        all(
            any(term in searchable for term in alternatives)
            for alternatives in technology_adolescence_groups
        )
        and (
            "adolescence of technology" in searchable
            or "technological adolescence" in searchable
        )
    )
    open_weights_evidence = (
        "nvidia",
        "amodei",
        "access",
        "competition",
        "control",
        "defenders",
        "attackers",
        "distillation",
        "safety testing",
    )
    open_weights = (
        ("open-weight" in searchable or "open weight" in searchable)
        and all(term in searchable for term in open_weights_evidence)
        and ("cannot be withdrawn" in searchable or "cannot pull them back" in searchable)
        and ("categorical ban" in searchable or "blanket ban" in searchable)
        and ("chip control" in searchable or "powerful chips" in searchable)
    )
    tls_handshake = (
        ("tls 1.3" in searchable or "tls1.3" in searchable)
        and ("clienthello" in searchable or "client hello" in searchable)
        and ("serverhello" in searchable or "server hello" in searchable)
        and "key share" in searchable
        and "derive" in searchable
        and "handshake traffic secret" in searchable
        and ("certificateverify" in searchable or "certificate verify" in searchable)
        and "finished message" in searchable
        and "application data" in searchable
        and "traffic keys" in searchable
    )
    mechanism_primitives = {
        "orbit_trace": "mechanism_orbit",
        "gradient_descent": "mechanism_gradient",
        "attention_flow": "mechanism_attention",
        "bayes_update": "mechanism_bayes",
    }
    primitive_counts = {
        primitive: sum(beat.primitive == primitive for beat in plan.beats)
        for primitive in mechanism_primitives
    }
    required_matches = max(2, len(plan.beats) - 1)
    dominant_primitive = next(
        (
            primitive
            for primitive, count in primitive_counts.items()
            if count >= required_matches
        ),
        None,
    )
    if elastic_llm_nesting:
        story_kind = "elastic_llm_nesting"
    elif lecun_world_model_bet:
        story_kind = "lecun_world_model_bet"
    elif technology_adolescence:
        story_kind = "technology_adolescence"
    elif open_weights:
        story_kind = "open_weights_debate"
    elif tls_handshake:
        story_kind = "mechanism_handshake"
    elif dominant_primitive is not None:
        story_kind = mechanism_primitives[dominant_primitive]
    elif _is_causal_sequence(plan):
        story_kind = "causal_explainer"
    else:
        story_kind = "generic_explainer"
    if story_kind == "mechanism_bayes" and not all(
        term in searchable
        for term in ("fair coin", "trick coin", "always lands heads", "two heads")
    ):
        story_kind = "generic_explainer"
        dominant_primitive = None
    core_labels = {
        "elastic_llm_nesting": "ONE MODEL, MANY SIZES",
        "lecun_world_model_bet": "WORDS → WORLD",
        "technology_adolescence": "POWER ↗ / MATURITY →",
        "open_weights_debate": "OPEN WEIGHTS",
        "mechanism_orbit": "ORBIT",
        "mechanism_gradient": "LOWER LOSS",
        "mechanism_attention": "CONTEXT",
        "mechanism_bayes": "POSTERIOR",
        "mechanism_handshake": "SECURE CHANNEL",
    }
    transition_mode = (
        "semantic_continuity"
        if (
            story_kind.startswith("mechanism_")
            or story_kind
            in {
                "elastic_llm_nesting",
                "lecun_world_model_bet",
                "technology_adolescence",
                "open_weights_debate",
                "causal_explainer",
            }
        )
        else "clean_swap"
    )
    text_transition_mode = (
        "persistent_lesson_header_handwritten_captions"
        if transition_mode == "semantic_continuity"
        else "beat_headline_swap"
    )
    hook_title = _persistent_hook_title(plan)
    feedback_contract = _feedback_loop_contract(plan)
    cycle_contract = _cycle_loop_contract(plan)
    source_visual_profile = (
        _source_visual_profile(searchable)
        if story_kind == "causal_explainer"
        else (
            "specialized_story_v1"
            if (
                story_kind.startswith("mechanism_")
                or story_kind
                in {
                    "elastic_llm_nesting",
                    "lecun_world_model_bet",
                    "technology_adolescence",
                    "open_weights_debate",
                }
            )
            else "generic_story_v1"
        )
    )
    topology_mode = "linear_journey"
    if story_kind == "causal_explainer":
        if feedback_contract["detected"]:
            topology_mode = "feedback_loop"
        elif cycle_contract["detected"]:
            topology_mode = "cycle_loop"
    recap_mode = (
        "full_route_sweep"
        if story_kind == "causal_explainer"
        else (
            "semantic_payoff_hold"
            if transition_mode == "semantic_continuity"
            else "none"
        )
    )
    claim_by_id = {claim.id: claim for claim in plan.claims}
    stages = []
    for index, beat in enumerate(plan.beats):
        mechanism_role = _process_role(plan, beat, index)
        source_text = " ".join(
            claim_by_id[claim_id].text
            for claim_id in beat.claim_ids
            if claim_id in claim_by_id
        )
        label = (
            _causal_step_label(plan, beat)
            if story_kind == "causal_explainer"
            else _causal_step_label(plan, beat, concise=False)
            if story_kind == "mechanism_handshake"
            else _visual_label(beat.headline, 4)
        )
        stages.append(
            {
                "id": beat.id,
                "role": beat.purpose.upper(),
                "label": label,
                "label_method": (
                    "source_action_object_compression_v1"
                    if story_kind == "causal_explainer"
                    else "specialized_story_label"
                ),
                "label_source_token_overlap": (
                    _label_source_token_overlap(label, source_text)
                    if story_kind == "causal_explainer"
                    else 0
                ),
                "detail": beat.on_screen_text,
                "source_label": beat.source_label,
                "sequence_index": index,
                "mechanism_role": mechanism_role,
            }
        )
    core_label = core_labels.get(story_kind, _visual_label(plan.topic, 5))
    if story_kind == "causal_explainer" and stages:
        core_label = (
            "PROBE ↻ ADJUST"
            if topology_mode == "feedback_loop"
            else "ONE CLOSED CYCLE"
            if topology_mode == "cycle_loop"
            else (
                str(stages[0]["mechanism_role"])
                + " → "
                + str(stages[-1]["mechanism_role"])
            )
        )
    return {
        "kind": story_kind,
        "core_label": core_label,
        "dominant_primitive": dominant_primitive,
        "transition_mode": transition_mode,
        "text_transition_mode": text_transition_mode,
        "hook_title_mode": "persistent_complete_hook",
        "hook_title": hook_title,
        "stage_label_render_mode": (
            "complete_scaled_two_line"
            if story_kind == "causal_explainer"
            else "standard_story_label"
        ),
        "topology_mode": topology_mode,
        "feedback_contract": feedback_contract,
        "cycle_contract": cycle_contract,
        "source_visual_profile": (
            "elastic_llm_nesting_v1"
            if story_kind == "elastic_llm_nesting"
            else "lecun_world_model_route_v1"
            if story_kind == "lecun_world_model_bet"
            else "technology_adolescence_v1"
            if story_kind == "technology_adolescence"
            else source_visual_profile
        ),
        "recap_mode": recap_mode,
        "motion_language": (
            "guided_camera_route_v1"
            if story_kind == "lecun_world_model_bet"
            else "nested_zoom_v1"
            if story_kind == "elastic_llm_nesting"
            else "one_shot_reveal_only_v1"
            if story_kind == "technology_adolescence"
            else "story_default"
        ),
        "chrome_mode": (
            "full_canvas_integrated_labels"
            if story_kind
            in {
                "elastic_llm_nesting",
                "lecun_world_model_bet",
            }
            else "minimal_title_only"
            if story_kind == "technology_adolescence"
            else "styled_story_chrome"
        ),
        "source_badge_mode": (
            "hidden"
            if story_kind
            in {
                "elastic_llm_nesting",
                "lecun_world_model_bet",
                "technology_adolescence",
            }
            else "visible"
        ),
        "stages": stages,
    }


def _caption_payload(
    cue: Optional[NarrationCue],
    fallback: str,
    duration: float,
    story_kind: str = "",
) -> List[Dict[str, object]]:
    if cue is None or not cue.words:
        return [{"text": fallback, "start_seconds": 0.0, "end_seconds": duration}]
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind
        in {
            "elastic_llm_nesting",
            "lecun_world_model_bet",
            "technology_adolescence",
            "open_weights_debate",
            "causal_explainer",
        }
    )
    maximum_words = (
        5
        if story_kind
        in {
            "elastic_llm_nesting",
            "lecun_world_model_bet",
            "technology_adolescence",
        }
        else 6
        if is_semantic_story
        else 4
    )
    maximum_duration = (
        2.2
        if story_kind
        in {
            "elastic_llm_nesting",
            "lecun_world_model_bet",
            "technology_adolescence",
        }
        else 2.5
        if is_semantic_story
        else 1.9
    )
    chunks: List[Dict[str, object]] = []
    current = []

    def flush_current() -> None:
        if not current:
            return
        payload: Dict[str, object] = {
            "text": " ".join(item.text for item in current),
            "start_seconds": round(current[0].start_seconds - cue.start_seconds, 4),
            "end_seconds": round(current[-1].end_seconds - cue.start_seconds, 4),
        }
        trigger_index = _semantic_trigger_word_index(current, story_kind)
        if trigger_index is not None:
            payload["emphasis_start_seconds"] = round(
                current[trigger_index].start_seconds - cue.start_seconds,
                4,
            )
            payload["emphasis_text"] = payload["text"]
        chunks.append(payload)
        current.clear()

    for word in cue.words:
        normalized_word = re.sub(r"[^a-z]", "", word.text.lower())
        if normalized_word.startswith(("multipl", "normaliz")):
            flush_current()
        current.append(word)
        chunk_duration = current[-1].end_seconds - current[0].start_seconds
        sentence_boundary = word.text.endswith((".", "!", "?"))
        should_close_sentence = (
            not is_semantic_story
            or len(current) >= 3
            or chunk_duration >= 0.85
        )
        if (
            len(current) >= maximum_words
            or chunk_duration >= maximum_duration
            or (sentence_boundary and should_close_sentence)
        ):
            flush_current()
    flush_current()
    if is_semantic_story and len(chunks) >= 2:
        balanced: List[Dict[str, object]] = []
        for chunk in chunks:
            chunk_words = len(str(chunk["text"]).split())
            if balanced and chunk_words <= 2:
                previous = balanced[-1]
                combined_words = (
                    len(str(previous["text"]).split()) + chunk_words
                )
                combined_duration = (
                    float(chunk["end_seconds"])
                    - float(previous["start_seconds"])
                )
                maximum_combined_words = (
                    6
                    if story_kind
                    in {
                        "elastic_llm_nesting",
                        "lecun_world_model_bet",
                        "technology_adolescence",
                    }
                    else 8
                )
                if (
                    combined_words <= maximum_combined_words
                    and combined_duration <= 3.2
                ):
                    previous["text"] = (
                        f"{previous['text']} {chunk['text']}"
                    )
                    previous["end_seconds"] = chunk["end_seconds"]
                    if (
                        "emphasis_start_seconds" not in previous
                        and "emphasis_start_seconds" in chunk
                    ):
                        previous["emphasis_start_seconds"] = chunk[
                            "emphasis_start_seconds"
                        ]
                    if "emphasis_start_seconds" in previous:
                        previous["emphasis_text"] = previous["text"]
                    continue
            balanced.append(chunk)
        chunks = balanced
    return chunks


def compile_manim_scene(
    plan: ContentPlan,
    narration: Optional[NarrationTrack] = None,
    animation_style: str = "hand_drawn",
) -> ManimSceneSpec:
    if plan.format != "video":
        raise ValueError("only video plans compile to ManimSceneSpec")
    if animation_style not in ANIMATION_STYLES:
        raise ValueError(f"unknown animation style: {animation_style}")
    elapsed = 0.0
    primitives: List[ManimPrimitiveSpec] = []
    cue_by_id = {cue.beat_id: cue for cue in narration.cues} if narration else {}
    story = _visual_story(plan)
    story_kind = str(story.get("kind", ""))
    for beat_index, beat in enumerate(plan.beats):
        cue = cue_by_id.get(beat.id)
        primitives.append(
            ManimPrimitiveSpec(
                kind=beat.primitive,
                title=beat.headline,
                body=beat.on_screen_text,
                claim_ids=beat.claim_ids,
                source_label=beat.source_label,
                start_seconds=elapsed,
                duration_seconds=beat.duration_seconds,
                params={
                    "purpose": beat.purpose,
                    "beat_index": beat_index,
                    "beat_count": len(plan.beats),
                    "captions": _caption_payload(
                        cue,
                        beat.narration,
                        beat.duration_seconds,
                        story_kind=story_kind,
                    ),
                },
            )
        )
        elapsed += beat.duration_seconds
    return ManimSceneSpec(
        id="manim_" + plan.id,
        width=1080,
        height=1920,
        fps=30,
        background=STYLE_BACKGROUNDS[animation_style],
        safe_zone=SAFE_ZONE.copy(),
        caption_rail=CAPTION_RAIL.copy(),
        primitives=primitives,
        duration_seconds=elapsed,
        animation_style=animation_style,
        story=story,
    )


def semantic_emphasis_summary(spec: ManimSceneSpec) -> Dict[str, object]:
    delays: List[float] = []
    invalid = 0
    caption_count = 0
    for primitive in spec.primitives:
        captions = primitive.params.get("captions", [])
        if not isinstance(captions, list):
            continue
        for caption in captions[1:]:
            if not isinstance(caption, dict):
                continue
            caption_count += 1
            if "emphasis_start_seconds" not in caption:
                continue
            try:
                caption_start = float(caption["start_seconds"])
                caption_end = float(caption["end_seconds"])
                emphasis_start = float(caption["emphasis_start_seconds"])
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
            if not caption_start <= emphasis_start <= caption_end:
                invalid += 1
                continue
            delays.append(emphasis_start - caption_start)
    ordered = sorted(delays)
    median = ordered[len(ordered) // 2] if ordered else 0.0
    return {
        "scheduled_event_count": len(delays),
        "eligible_caption_count": caption_count,
        "delayed_event_count": sum(delay > 0.02 for delay in delays),
        "invalid_event_count": invalid,
        "median_trigger_delay_seconds": round(median, 4),
        "max_trigger_delay_seconds": round(max(delays) if delays else 0.0, 4),
        "method": "aligned_word_trigger_v1",
    }


def semantic_text_transition_summary(
    spec: ManimSceneSpec,
) -> Dict[str, object]:
    story_kind = str(spec.story.get("kind", ""))
    is_semantic_story = (
        story_kind.startswith("mechanism_")
        or story_kind
        in {
            "technology_adolescence",
            "open_weights_debate",
            "causal_explainer",
        }
    )
    if not is_semantic_story:
        return {}
    dwell_times: List[float] = []
    caption_count = 0
    for primitive in spec.primitives:
        captions = primitive.params.get("captions", [])
        if not isinstance(captions, list):
            continue
        caption_count += len(captions)
        for caption in captions:
            if not isinstance(caption, dict):
                continue
            try:
                dwell_times.append(
                    max(
                        0.0,
                        float(caption["end_seconds"])
                        - float(caption["start_seconds"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    transition_count = max(0, caption_count - 1)
    duration_minutes = max(0.01, spec.duration_seconds / 60)
    rapid_count = sum(value < 0.65 for value in dwell_times)
    hook_title = spec.story.get("hook_title")
    hook_title = hook_title if isinstance(hook_title, dict) else {}
    title_text = str(hook_title.get("text", ""))
    stage_items = spec.story.get("stages")
    stage_items = stage_items if isinstance(stage_items, list) else []
    stage_labels = [
        str(item.get("label", ""))
        for item in stage_items
        if isinstance(item, dict)
    ]
    stage_overlaps = [
        int(item.get("label_source_token_overlap", 0))
        for item in stage_items
        if isinstance(item, dict)
    ]
    stage_methods = [
        str(item.get("label_method", ""))
        for item in stage_items
        if isinstance(item, dict)
    ]
    return {
        "mode": str(spec.story.get("text_transition_mode", "")),
        "hook_title_mode": str(spec.story.get("hook_title_mode", "")),
        "hook_title": title_text,
        "hook_title_source": str(hook_title.get("source", "")),
        "hook_title_contains_ellipsis": (
            "…" in title_text or "..." in title_text
        ),
        "hook_title_matches_plan_hook": bool(
            hook_title.get("matches_plan_hook", False)
        ),
        "hook_title_word_count": len(title_text.split()),
        "stage_label_render_mode": str(
            spec.story.get("stage_label_render_mode", "")
        ),
        "stage_label_count": len(stage_labels),
        "stage_label_ellipsis_count": sum(
            "…" in label or "..." in label
            for label in stage_labels
        ),
        "maximum_stage_label_words": max(
            (
                len(
                    re.findall(
                        r"[A-Za-z0-9][A-Za-z0-9'+.-]*",
                        label,
                    )
                )
                for label in stage_labels
            ),
            default=0,
        ),
        "minimum_stage_label_source_overlap": (
            min(stage_overlaps) if stage_overlaps else 0
        ),
        "stage_label_method_count": sum(
            method == "source_action_object_compression_v1"
            for method in stage_methods
        ),
        "topology_mode": str(spec.story.get("topology_mode", "")),
        "source_visual_profile": str(
            spec.story.get("source_visual_profile", "")
        ),
        "motion_language": str(spec.story.get("motion_language", "")),
        "chrome_mode": str(spec.story.get("chrome_mode", "")),
        "source_badge_mode": str(spec.story.get("source_badge_mode", "")),
        "feedback_contract_mode": str(
            (
                spec.story.get("feedback_contract")
                if isinstance(spec.story.get("feedback_contract"), dict)
                else {}
            ).get("mode", "")
        ),
        "feedback_evidence_stage_count": int(
            (
                spec.story.get("feedback_contract")
                if isinstance(spec.story.get("feedback_contract"), dict)
                else {}
            ).get("evidence_stage_count", 0)
        ),
        "feedback_shared_state_token_count": len(
            (
                spec.story.get("feedback_contract")
                if isinstance(spec.story.get("feedback_contract"), dict)
                else {}
            ).get("shared_state_tokens", [])
        ),
        "cycle_contract_mode": str(
            (
                spec.story.get("cycle_contract")
                if isinstance(spec.story.get("cycle_contract"), dict)
                else {}
            ).get("mode", "")
        ),
        "cycle_evidence_stage_count": int(
            (
                spec.story.get("cycle_contract")
                if isinstance(spec.story.get("cycle_contract"), dict)
                else {}
            ).get("evidence_stage_count", 0)
        ),
        "cycle_shared_state_token_count": len(
            (
                spec.story.get("cycle_contract")
                if isinstance(spec.story.get("cycle_contract"), dict)
                else {}
            ).get("shared_state_tokens", [])
        ),
        "recap_mode": str(spec.story.get("recap_mode", "")),
        "headline_replacement_count": 0,
        "caption_cue_count": caption_count,
        "caption_transition_count": transition_count,
        "caption_transitions_per_minute": round(
            transition_count / duration_minutes,
            2,
        ),
        "median_caption_dwell_seconds": round(
            statistics.median(dwell_times) if dwell_times else 0.0,
            4,
        ),
        "average_caption_dwell_seconds": round(
            statistics.fmean(dwell_times) if dwell_times else 0.0,
            4,
        ),
        "rapid_caption_count": rapid_count,
        "rapid_caption_ratio": round(
            rapid_count / max(1, len(dwell_times)),
            4,
        ),
        "method": "persistent_header_six_word_handwritten_caption_cadence_v1",
    }


def write_manim_spec(job_dir: Path, spec: ManimSceneSpec) -> Path:
    path = job_dir / "video" / "manim" / "spec.json"
    write_json(path, spec)
    return path


def _legacy_scene_source(spec: ManimSceneSpec) -> str:
    payload = json.dumps(
        {
            "background": spec.background,
            "primitives": [
                {
                    "kind": item.kind,
                    "title": item.title,
                    "body": item.body,
                    "source_label": item.source_label,
                    "duration_seconds": item.duration_seconds,
                    "params": item.params,
                }
                for item in spec.primitives
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f'''# Generated by contentmaxxer. Manual edits are safe; `render` preserves bespoke scenes.
import json
import textwrap
from manim import *

config.pixel_width = {spec.width}
config.pixel_height = {spec.height}
config.frame_rate = {spec.fps}
config.frame_width = 9
config.frame_height = 16
SPEC = json.loads({payload!r})
INK = "#F4F7FB"
MUTED = "#A8B3C4"
ACCENT = "#5EEAD4"
PANEL = "#122238"
PANEL_2 = "#0B1829"
WARM = "#FBBF24"
PINK = "#FB7185"


def fitted_text(value, max_width=7.4, size=48, color=INK, weight=NORMAL):
    text = Text(value, font_size=size, color=color, weight=weight, line_spacing=0.9)
    if text.width > max_width:
        text.scale_to_fit_width(max_width)
    return text


def wrapped_text(value, max_width=7.15, max_height=1.3, chars=25, lines=2, size=43, color=INK, weight=BOLD):
    wrapped = textwrap.wrap(value, width=chars, break_long_words=False, break_on_hyphens=False)
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] = wrapped[-1].rstrip(" .,;:") + "…"
    text = Text("\\n".join(wrapped), font_size=size, color=color, weight=weight, line_spacing=0.78)
    if text.width > max_width:
        text.scale_to_fit_width(max_width)
    if text.height > max_height:
        text.scale_to_fit_height(max_height)
    return text


def source_badge(label):
    badge = RoundedRectangle(corner_radius=0.12, width=3.4, height=0.38, fill_color=PANEL, fill_opacity=0.92, stroke_opacity=0)
    text = fitted_text("SOURCE  " + label, max_width=3.05, size=18, color=MUTED)
    return VGroup(badge, text).move_to(UP * 4.28 + LEFT * 1.9)


def model_cards(item):
    names = ["SOL", "TERRA", "LUNA"]
    cards = VGroup(*[
        VGroup(
            RoundedRectangle(corner_radius=0.18, width=2.25, height=2.55, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT),
            fitted_text(name, max_width=1.8, size=28, color=ACCENT, weight=BOLD),
        ) for name in names
    ]).arrange(RIGHT, buff=0.28)
    for card in cards:
        card[1].move_to(card[0].get_center())
    return cards


def orbit_trace(item):
    stage = int(item.get("params", {{}}).get("beat_index", 0))
    earth = Circle(radius=1.22, color="#60A5FA", fill_color="#1D4ED8", fill_opacity=0.28)
    atmosphere = Circle(radius=1.38, color="#60A5FA", stroke_opacity=0.22)
    orbit = Ellipse(width=6.15, height=3.45, color=ACCENT, stroke_opacity=0.18 if stage < 2 else 0.72)
    low_path = ArcBetweenPoints(LEFT * 2.7 + UP * 0.15, RIGHT * 2.35 + DOWN * 1.25, angle=-0.5, color=PINK, stroke_opacity=0.48 if stage == 3 else 0.0)
    escape_path = ArcBetweenPoints(LEFT * 2.7 + UP * 0.2, RIGHT * 3.0 + UP * 1.15, angle=0.35, color=WARM, stroke_opacity=0.48 if stage == 3 else 0.0)
    satellite = Dot(orbit.point_from_proportion(0.12), radius=0.11, color=WARM)
    gravity = Arrow(
        satellite.get_center(), earth.get_center(), buff=0.16, color=PINK, stroke_width=5,
        stroke_opacity=1.0,
    )
    velocity = Arrow(
        satellite.get_center(), satellite.get_center() + RIGHT * 1.25 + UP * 0.25,
        buff=0.05, color=WARM, stroke_width=5, stroke_opacity=0.05 if stage < 1 else 1.0,
    )
    gravity_label = fitted_text("gravity pulls inward", size=22, color=PINK).next_to(gravity, LEFT, buff=0.08)
    velocity_label = fitted_text("sideways speed", size=22, color=WARM).next_to(velocity, UP, buff=0.08)
    velocity_label.set_opacity(0.05 if stage < 1 else 1.0)
    stage_labels = ["falling inward", "add sideways speed", "the path keeps curving", "speed changes the path", "falling around Earth"]
    summary = fitted_text(
        stage_labels[min(stage, len(stage_labels) - 1)],
        size=28, color=ACCENT, weight=BOLD,
    ).next_to(earth, DOWN, buff=1.05)
    return VGroup(orbit, low_path, escape_path, atmosphere, earth, satellite, gravity, velocity, gravity_label, velocity_label, summary)


def vector_transform(item):
    origin = Dot(LEFT * 2.3 + DOWN * 0.6, color=INK)
    down = Arrow(origin, origin.get_center() + DOWN * 2.0, buff=0.08, color=PINK, stroke_width=7)
    side = Arrow(origin, origin.get_center() + RIGHT * 2.8, buff=0.08, color=WARM, stroke_width=7)
    curve = ArcBetweenPoints(origin.get_center(), RIGHT * 2.45 + DOWN * 1.65, angle=-0.72, color=ACCENT, stroke_width=7)
    labels = VGroup(
        fitted_text("fall", size=24, color=PINK).next_to(down, LEFT),
        fitted_text("forward", size=24, color=WARM).next_to(side, UP),
        fitted_text("orbit", size=28, color=ACCENT, weight=BOLD).next_to(curve, DOWN),
    )
    return VGroup(origin, down, side, curve, labels)


def gradient_descent(item):
    stage = int(item.get("params", {{}}).get("beat_index", 0))
    axes = Axes(
        x_range=[-3, 3, 1],
        y_range=[0, 5, 1],
        x_length=6.5,
        y_length=4.2,
        axis_config={{"color": MUTED, "stroke_opacity": 0.35, "include_ticks": False}},
    )
    curve = axes.plot(lambda x: 0.42 * x * x + 0.35, x_range=[-2.8, 2.8], color=ACCENT, stroke_width=7)
    point_data = ((-2.45, PINK), (-1.55, WARM), (-0.82, ACCENT), (-0.25, INK))
    points = VGroup()
    for index, (x, color) in enumerate(point_data):
        point = Dot(axes.c2p(x, 0.42 * x * x + 0.35), color=color, radius=0.1)
        point.set_opacity(1.0 if index <= stage else 0.13)
        points.add(point)
    arrows = VGroup()
    for index in range(len(points) - 1):
        arrow = Arrow(points[index], points[index + 1], buff=0.16, color=WARM, stroke_width=4)
        arrow.set_opacity(1.0 if index < stage else 0.12)
        arrows.add(arrow)
    tangent = Arrow(
        axes.c2p(-2.45, 2.87), axes.c2p(-1.15, 1.35), buff=0.05,
        color=PINK, stroke_width=5,
    ).set_opacity(1.0 if stage <= 1 else 0.24)
    stage_labels = ["measure the error", "follow the negative gradient", "recalculate and step", "step size matters", "repeat toward lower loss"]
    summary = fitted_text(
        stage_labels[min(stage, len(stage_labels) - 1)],
        size=27, color=ACCENT, weight=BOLD,
    ).next_to(axes, DOWN, buff=0.35)
    return VGroup(axes, curve, tangent, arrows, points, summary)


def attention_flow(item):
    stage = int(item.get("params", {{}}).get("beat_index", 0))
    tokens = ["the", "bank", "was", "steep"]
    token_boxes = VGroup(*[
        VGroup(
            RoundedRectangle(corner_radius=0.12, width=1.35, height=0.72, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT),
            fitted_text(token, max_width=1.05, size=24),
        )
        for token in tokens
    ]).arrange(RIGHT, buff=0.22)
    for box in token_boxes:
        box[1].move_to(box[0])
    focus = token_boxes[1]
    arc_strengths = (
        (token_boxes[0], MUTED, 3, 0.25),
        (token_boxes[2], WARM, 5, 0.62),
        (token_boxes[3], PINK, 7, 1.0),
    )
    arcs = VGroup()
    for target, color, width, strength in arc_strengths:
        arc = CurvedArrow(focus.get_top(), target.get_top(), angle=0.62, color=color, stroke_width=width)
        arc.set_opacity(0.12 if stage == 0 else (0.55 if stage == 1 else strength))
        arcs.add(arc)
    second_focus = token_boxes[2]
    parallel_head = VGroup(
        CurvedArrow(second_focus.get_bottom(), token_boxes[0].get_bottom(), angle=-0.62, color=ACCENT, stroke_width=4),
        CurvedArrow(second_focus.get_bottom(), token_boxes[3].get_bottom(), angle=0.62, color=WARM, stroke_width=6),
    )
    parallel_head.set_opacity(0.72 if stage >= 4 else 0.0)
    mixer = VGroup(
        Circle(radius=0.34, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT),
        fitted_text("Σ", size=27, color=ACCENT, weight=BOLD),
    ).arrange().next_to(token_boxes, RIGHT, buff=0.48)
    mixer[1].move_to(mixer[0])
    mixer.set_opacity(1.0 if stage >= 3 else 0.0)
    focus[0].set_stroke(PINK if stage >= 1 else ACCENT, width=5 if stage >= 1 else 2)
    stage_labels = ["make query, key, value", "compare query with keys", "softmax makes weights", "mix the weighted values", "heads learn different links"]
    label = fitted_text(
        stage_labels[min(stage, len(stage_labels) - 1)],
        size=27, color=ACCENT, weight=BOLD,
    ).next_to(token_boxes, DOWN, buff=0.85)
    return VGroup(token_boxes, arcs, parallel_head, mixer, label)


def timeline(item):
    line = Line(LEFT * 3.2, RIGHT * 3.2, color=ACCENT)
    dots = VGroup(*[Dot(line.point_from_proportion(x), color=ACCENT) for x in (0.0, 0.5, 1.0)])
    return VGroup(line, dots)


def comparison_grid(item):
    return VGroup(*[
        RoundedRectangle(corner_radius=0.12, width=3.25, height=1.15, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT)
        for _ in range(4)
    ]).arrange_in_grid(rows=2, cols=2, buff=0.25)


def tokens_context(item):
    tokens = VGroup(*[Square(0.32, fill_color=ACCENT, fill_opacity=0.8, stroke_opacity=0) for _ in range(12)])
    return tokens.arrange_in_grid(rows=3, cols=4, buff=0.12)


def eval_bars(item):
    bars = VGroup(*[Rectangle(width=w, height=0.35, fill_color=ACCENT, fill_opacity=0.85, stroke_opacity=0) for w in (2.3, 3.4, 4.8)])
    return bars.arrange(DOWN, aligned_edge=LEFT, buff=0.22)


def agent_loop(item):
    nodes = VGroup(*[Circle(0.43, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT) for _ in range(4)])
    nodes.arrange_in_grid(rows=2, cols=2, buff=1.0)
    arrows = VGroup(Arrow(nodes[0], nodes[1], buff=0.45), Arrow(nodes[1], nodes[3], buff=0.45), Arrow(nodes[3], nodes[2], buff=0.45), Arrow(nodes[2], nodes[0], buff=0.45))
    return VGroup(nodes, arrows)


def claim_callout(item):
    return RoundedRectangle(corner_radius=0.2, width=7.2, height=2.7, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT)


def routing_diagram(item):
    center = Circle(0.48, fill_color=ACCENT, fill_opacity=1, stroke_opacity=0)
    targets = VGroup(*[RoundedRectangle(corner_radius=0.1, width=1.6, height=0.7, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT) for _ in range(3)]).arrange(DOWN, buff=0.35).shift(RIGHT * 2.2)
    arrows = VGroup(*[Arrow(center, target, buff=0.45, stroke_width=3) for target in targets])
    return VGroup(center, targets, arrows)


def before_after(item):
    left = RoundedRectangle(corner_radius=0.16, width=3.1, height=2.1, fill_color=PANEL, fill_opacity=1, stroke_color=MUTED)
    right = RoundedRectangle(corner_radius=0.16, width=3.1, height=2.1, fill_color=PANEL, fill_opacity=1, stroke_color=ACCENT)
    arrow = Arrow(left, right, buff=0.25, color=ACCENT)
    return VGroup(left, arrow, right).arrange(RIGHT, buff=0.25)


PRIMITIVES = {{
    "model_cards": model_cards,
    "timeline": timeline,
    "comparison_grid": comparison_grid,
    "tokens_context": tokens_context,
    "eval_bars": eval_bars,
    "agent_loop": agent_loop,
    "claim_callout": claim_callout,
    "routing_diagram": routing_diagram,
    "before_after": before_after,
    "orbit_trace": orbit_trace,
    "vector_transform": vector_transform,
    "gradient_descent": gradient_descent,
    "attention_flow": attention_flow,
}}


class ContentMaxxerScene(Scene):
    def construct(self):
        self.camera.background_color = SPEC["background"]
        grid = NumberPlane(
            x_range=[-5, 5, 1],
            y_range=[-9, 9, 1],
            background_line_style={{"stroke_color": "#20354D", "stroke_opacity": 0.13, "stroke_width": 1}},
            axis_config={{"stroke_opacity": 0}},
        )
        self.add(grid)
        current_title = None
        current_visual = None
        current_badge = None
        current_caption = None
        caption_panel = RoundedRectangle(
            corner_radius=0.18,
            width=7.45,
            height=1.28,
            fill_color=PANEL_2,
            fill_opacity=0.98,
            stroke_color="#20354D",
            stroke_opacity=0.8,
        ).move_to(DOWN * 4.68)
        self.add(caption_panel)
        for beat_index, item in enumerate(SPEC["primitives"]):
            beat_origin = self.time
            duration = max(0.2, item["duration_seconds"])
            title = wrapped_text(item["title"], size=43, weight=BOLD).move_to(UP * 5.35)
            visual = PRIMITIVES.get(item["kind"], claim_callout)(item).move_to(UP * 0.55)
            badge = source_badge(item["source_label"])
            captions = item.get("params", {{}}).get("captions", [])
            first_caption_text = captions[0]["text"] if captions else item["body"]
            caption = wrapped_text(
                first_caption_text, max_width=6.75, max_height=0.92, chars=25, lines=2, size=35, weight=BOLD,
            ).move_to(caption_panel)
            if current_title is None:
                self.play(
                    FadeIn(title, shift=UP * 0.12),
                    LaggedStart(*[Create(part) for part in visual], lag_ratio=0.08),
                    FadeIn(badge),
                    FadeIn(caption),
                    run_time=min(0.9, duration * 0.2),
                )
            else:
                self.remove(current_title, current_caption)
                self.add(title, caption)
                self.play(
                    ReplacementTransform(current_visual, visual),
                    Transform(current_badge, badge),
                    run_time=min(0.72, duration * 0.16),
                )
            current_title = title
            current_visual = visual
            current_badge = badge if current_badge is None else current_badge
            current_caption = caption
            for caption_index, cue in enumerate(captions[1:], start=1):
                target = beat_origin + cue["start_seconds"]
                if self.time < target:
                    self.wait(target - self.time)
                replacement = wrapped_text(
                    cue["text"], max_width=6.75, max_height=0.92, chars=25, lines=2, size=35, weight=BOLD,
                ).move_to(caption_panel)
                self.remove(current_caption)
                self.add(replacement)
                current_caption = replacement
                animations = []
                if caption_index % 2:
                    animations.append(Indicate(current_visual, color=WARM, scale_factor=1.025))
                if animations:
                    self.play(*animations, run_time=min(0.22, max(0.12, cue["end_seconds"] - cue["start_seconds"])))
            beat_end = beat_origin + duration
            if self.time < beat_end:
                self.wait(beat_end - self.time)
        if current_title is not None:
            self.play(
                FadeOut(VGroup(current_title, current_visual, current_badge, current_caption, caption_panel)),
                run_time=0.35,
            )
'''


HAND_DRAWN_SCENE_LIBRARY = r'''

HAND_FONT = "Chalkboard SE"
MARKER_FONT = "Marker Felt"
CHALK = "#F7F3E8"
TEAL = "#67E8D4"
BLUE = "#74A7FF"
GOLD = "#F9C74F"
CORAL = "#FF718A"
VIOLET = "#C4A7FF"
BOARD = "#081521"
BOARD_EDGE = "#29445C"


def fitted_text(value, max_width=7.4, size=48, color=CHALK, weight=NORMAL, font=HAND_FONT):
    text = Text(value, font=font, font_size=size, color=color, weight=weight, line_spacing=0.88)
    if text.width > max_width:
        text.scale_to_fit_width(max_width)
    return text


def wrapped_text(value, max_width=7.15, max_height=1.3, chars=25, lines=2, size=43, color=CHALK, weight=BOLD, font=HAND_FONT):
    wrapped = textwrap.wrap(value, width=chars, break_long_words=False, break_on_hyphens=False)
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] = wrapped[-1].rstrip(" .,;:") + "…"
    text = Text("\n".join(wrapped), font=font, font_size=size, color=color, weight=weight, line_spacing=0.72)
    if text.width > max_width:
        text.scale_to_fit_width(max_width)
    if text.height > max_height:
        text.scale_to_fit_height(max_height)
    return text


def _jitter(point, index, seed, amount):
    phase = (index + 1) * (seed + 1.73)
    return np.array(point, dtype=float) + np.array([
        amount * np.sin(phase * 1.91),
        amount * np.cos(phase * 1.37),
        0.0,
    ])


def rough_path(points, color=CHALK, width=4, seed=1, closed=False, fill_color=None, fill_opacity=0.0, passes=3):
    raw = [np.array(point, dtype=float) for point in points]
    strokes = VGroup()
    for pass_index in range(passes):
        amount = 0.012 + pass_index * 0.005
        jittered = [_jitter(point, index, seed + pass_index * 7, amount) for index, point in enumerate(raw)]
        if closed:
            jittered.append(jittered[0])
        path = VMobject()
        if len(raw) <= 4:
            path.set_points_as_corners(jittered)
        else:
            path.set_points_smoothly(jittered)
        opacity = 0.82 if pass_index == 0 else 0.30
        path.set_stroke(color, width=max(1.0, width - pass_index * 0.7), opacity=opacity)
        if pass_index == 0 and fill_opacity:
            path.set_fill(fill_color or color, opacity=fill_opacity)
        strokes.add(path)
    return strokes


def rough_line(start, end, color=CHALK, width=4, seed=1):
    start = np.array(start, dtype=float)
    end = np.array(end, dtype=float)
    points = [interpolate(start, end, alpha) for alpha in (0.0, 0.24, 0.5, 0.76, 1.0)]
    return rough_path(points, color=color, width=width, seed=seed)


def rough_arrow(start, end, color=CHALK, width=5, seed=1):
    start = np.array(start, dtype=float)
    end = np.array(end, dtype=float)
    shaft = rough_line(start, end, color=color, width=width, seed=seed)
    direction = end - start
    angle = np.arctan2(direction[1], direction[0])
    tip = Triangle(fill_color=color, fill_opacity=0.95, stroke_opacity=0).scale(0.13)
    tip.rotate(angle - PI / 2).move_to(end)
    ghost = tip.copy().scale(0.93).shift(LEFT * 0.018 + DOWN * 0.012).set_opacity(0.35)
    return VGroup(shaft, tip, ghost)


def rough_ellipse(width, height, center=ORIGIN, color=CHALK, stroke_width=4, seed=1, fill_color=None, fill_opacity=0.0):
    points = []
    for index in range(49):
        angle = TAU * index / 48
        points.append(np.array([
            center[0] + width * 0.5 * np.cos(angle),
            center[1] + height * 0.5 * np.sin(angle),
            0.0,
        ]))
    return rough_path(
        points,
        color=color,
        width=stroke_width,
        seed=seed,
        closed=True,
        fill_color=fill_color,
        fill_opacity=fill_opacity,
    )


def rough_circle(radius, center=ORIGIN, color=CHALK, stroke_width=4, seed=1, fill_color=None, fill_opacity=0.0):
    return rough_ellipse(
        radius * 2,
        radius * 2,
        center=center,
        color=color,
        stroke_width=stroke_width,
        seed=seed,
        fill_color=fill_color,
        fill_opacity=fill_opacity,
    )


def rough_rect(width, height, center=ORIGIN, color=BOARD_EDGE, stroke_width=3, seed=1, fill_color=None, fill_opacity=0.0):
    x, y = center[0], center[1]
    points = [
        np.array([x - width / 2, y - height / 2, 0.0]),
        np.array([x + width / 2, y - height / 2, 0.0]),
        np.array([x + width / 2, y + height / 2, 0.0]),
        np.array([x - width / 2, y + height / 2, 0.0]),
    ]
    return rough_path(
        points,
        color=color,
        width=stroke_width,
        seed=seed,
        closed=True,
        fill_color=fill_color,
        fill_opacity=fill_opacity,
    )


def hand_label(value, center, color=CHALK, size=24, max_width=2.8, font=HAND_FONT):
    return fitted_text(value, max_width=max_width, size=size, color=color, weight=BOLD, font=font).move_to(center)


def sticky_note(value, center, width=2.65, height=0.78, color=GOLD, seed=1, size=22):
    frame = rough_rect(
        width,
        height,
        center=center,
        color=color,
        stroke_width=3,
        seed=seed,
        fill_color=color,
        fill_opacity=0.08,
    )
    text = wrapped_text(
        value,
        max_width=width - 0.25,
        max_height=height - 0.18,
        chars=20,
        lines=2,
        size=size,
        color=color,
        font=HAND_FONT,
    ).move_to(center)
    tape = rough_line(
        center + LEFT * 0.34 + UP * (height / 2 + 0.04),
        center + RIGHT * 0.34 + UP * (height / 2 + 0.04),
        color=CHALK,
        width=5,
        seed=seed + 31,
    ).set_opacity(0.22)
    return VGroup(frame, text, tape)


def stage_rail(stage):
    dots = VGroup()
    for index in range(5):
        center = np.array([3.48, 2.25 - index * 1.12, 0.0])
        color = GOLD if index == stage else BOARD_EDGE
        dot = rough_circle(
            0.105 if index == stage else 0.075,
            center=center,
            color=color,
            stroke_width=3,
            seed=90 + index,
            fill_color=color,
            fill_opacity=0.78 if index == stage else 0.10,
        )
        dots.add(dot)
    return dots


def visual_board(stage, content, cue_targets=None, highlight_path=None):
    board = rough_rect(
        7.72,
        6.68,
        center=ORIGIN,
        color=BOARD_EDGE,
        stroke_width=2.6,
        seed=300 + stage,
        fill_color=BOARD,
        fill_opacity=0.34,
    )
    corner = hand_label(f"SKETCH {stage + 1}/5", LEFT * 2.92 + UP * 2.92, color=MUTED, size=15, max_width=1.35)
    underline = rough_line(
        LEFT * 3.48 + UP * 2.69,
        LEFT * 2.42 + UP * 2.69,
        color=MUTED,
        width=2,
        seed=330 + stage,
    )
    result = VGroup(board, content, stage_rail(stage), corner, underline)
    result.cue_targets = list(cue_targets or [content])
    result.highlight_path = highlight_path
    return result


def source_badge(label):
    center = UP * 4.28 + LEFT * 2.15
    frame = rough_rect(
        3.0,
        0.42,
        center=center,
        color=BOARD_EDGE,
        stroke_width=2,
        seed=401,
        fill_color=PANEL,
        fill_opacity=0.55,
    )
    text = fitted_text("SOURCE  " + label, max_width=2.68, size=17, color=MUTED, font=HAND_FONT).move_to(center)
    return VGroup(frame, text)


def _mini_earth(center, radius=0.72, seed=1):
    globe = rough_circle(
        radius,
        center=center,
        color=BLUE,
        stroke_width=4,
        seed=seed,
        fill_color="#153B7A",
        fill_opacity=0.42,
    )
    land = rough_path(
        [
            center + LEFT * radius * 0.48 + UP * radius * 0.12,
            center + LEFT * radius * 0.1 + UP * radius * 0.35,
            center + RIGHT * radius * 0.34 + UP * radius * 0.05,
            center + RIGHT * radius * 0.08 + DOWN * radius * 0.25,
            center + LEFT * radius * 0.32 + DOWN * radius * 0.12,
        ],
        color=TEAL,
        width=2.2,
        seed=seed + 12,
    ).set_opacity(0.42)
    return VGroup(globe, land)


def orbit_trace(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    cue_targets = []
    highlight = None

    if stage == 0:
        earth_center = LEFT * 0.65 + DOWN * 0.48
        earth = _mini_earth(earth_center, radius=1.02, seed=10)
        satellite = Dot(RIGHT * 1.35 + UP * 1.25, radius=0.11, color=GOLD)
        gravity = rough_arrow(satellite.get_center(), earth_center + UP * 0.18, color=CORAL, width=5, seed=13)
        trail = VGroup(*[
            Dot(interpolate(satellite.get_center(), earth_center, alpha), radius=0.035, color=CORAL).set_opacity(0.18 + alpha * 0.5)
            for alpha in (0.16, 0.30, 0.44, 0.58)
        ])
        note = sticky_note("gravity keeps pulling", RIGHT * 1.63 + DOWN * 1.63, width=2.55, color=CORAL, seed=15)
        label = hand_label("always falling", LEFT * 2.1 + UP * 1.62, color=CORAL, size=27, max_width=2.2, font=MARKER_FONT)
        content = VGroup(earth, satellite, gravity, trail, note, label)
        cue_targets = [gravity, earth, note, satellite]
        highlight = gravity[0][0]
    elif stage == 1:
        left_center = LEFT * 1.78
        right_center = RIGHT * 1.78
        left_card = rough_rect(3.05, 3.72, center=left_center, color=CORAL, seed=20, fill_color=PANEL, fill_opacity=0.32)
        right_card = rough_rect(3.05, 3.72, center=right_center, color=GOLD, seed=21, fill_color=PANEL, fill_opacity=0.32)
        earth = _mini_earth(left_center + DOWN * 0.52, radius=0.72, seed=22)
        falling_dot = Dot(left_center + UP * 0.82, radius=0.09, color=CORAL)
        fall_arrow = rough_arrow(falling_dot.get_center(), left_center + DOWN * 0.1, color=CORAL, width=4.5, seed=23)
        fall_label = hand_label("1. FALL", left_center + UP * 1.42, color=CORAL, size=27, max_width=2.2, font=MARKER_FONT)
        horizon = rough_path(
            [
                right_center + LEFT * 1.1 + DOWN * 0.62,
                right_center + LEFT * 0.5 + DOWN * 0.78,
                right_center + RIGHT * 0.2 + DOWN * 0.82,
                right_center + RIGHT * 1.1 + DOWN * 0.58,
            ],
            color=BLUE,
            width=3,
            seed=24,
        )
        side_dot = Dot(right_center + LEFT * 0.82 + UP * 0.38, radius=0.09, color=GOLD)
        side_arrow = rough_arrow(side_dot.get_center(), right_center + RIGHT * 0.82 + UP * 0.38, color=GOLD, width=4.5, seed=25)
        side_label = hand_label("2. FORWARD", right_center + UP * 1.42, color=GOLD, size=27, max_width=2.35, font=MARKER_FONT)
        plus = hand_label("+", UP * 0.15, color=CHALK, size=48, max_width=0.5, font=MARKER_FONT)
        content = VGroup(left_card, right_card, earth, falling_dot, fall_arrow, fall_label, horizon, side_dot, side_arrow, side_label, plus)
        cue_targets = [fall_arrow, side_arrow, plus, horizon]
        highlight = side_arrow[0][0]
    elif stage == 2:
        earth_center = DOWN * 0.35
        earth = _mini_earth(earth_center, radius=1.02, seed=30)
        orbit = rough_ellipse(5.8, 3.35, center=earth_center, color=TEAL, stroke_width=4.5, seed=31)
        satellite_point = np.array([2.38, 0.62, 0.0])
        satellite = Dot(satellite_point, radius=0.115, color=GOLD)
        gravity = rough_arrow(satellite_point, earth_center + RIGHT * 0.32, color=CORAL, width=4.5, seed=32)
        velocity = rough_arrow(satellite_point, satellite_point + RIGHT * 1.05 + UP * 0.25, color=GOLD, width=4.5, seed=33)
        equation = sticky_note("fall + forward = curve", UP * 2.05, width=3.85, color=TEAL, seed=34, size=24)
        gravity_label = hand_label("gravity", RIGHT * 0.55 + UP * 0.78, color=CORAL, size=20, max_width=1.2)
        velocity_label = hand_label("speed", RIGHT * 2.73 + UP * 1.23, color=GOLD, size=20, max_width=1.0)
        content = VGroup(orbit, earth, satellite, gravity, velocity, equation, gravity_label, velocity_label)
        cue_targets = [equation, gravity, velocity, orbit]
        highlight = orbit[0]
    elif stage == 3:
        earth_center = DOWN * 0.82
        earth = _mini_earth(earth_center, radius=0.88, seed=40)
        start = LEFT * 3.05 + UP * 1.48
        slow = rough_path(
            [start, LEFT * 1.8 + UP * 0.95, LEFT * 0.65 + UP * 0.1, earth_center + LEFT * 0.28],
            color=CORAL,
            width=4,
            seed=41,
        )
        orbit = rough_ellipse(5.25, 2.75, center=earth_center, color=TEAL, stroke_width=4.5, seed=42)
        fast = rough_path(
            [start + DOWN * 0.24, LEFT * 1.0 + UP * 1.44, RIGHT * 1.0 + UP * 1.62, RIGHT * 3.0 + UP * 1.95],
            color=GOLD,
            width=4,
            seed=43,
        )
        labels = VGroup(
            hand_label("too slow → hits", LEFT * 2.05 + DOWN * 0.1, color=CORAL, size=21, max_width=2.0),
            hand_label("just right → orbit", RIGHT * 1.95 + DOWN * 2.15, color=TEAL, size=21, max_width=2.2),
            hand_label("faster → opens", RIGHT * 2.08 + UP * 2.23, color=GOLD, size=21, max_width=2.0),
        )
        speed_note = sticky_note("speed chooses the path", LEFT * 1.7 + UP * 2.35, width=3.25, color=GOLD, seed=44)
        content = VGroup(earth, slow, orbit, fast, labels, speed_note)
        cue_targets = [slow, orbit, fast, speed_note]
        highlight = orbit[0]
    else:
        earth_center = LEFT * 1.08 + DOWN * 0.28
        earth = _mini_earth(earth_center, radius=1.0, seed=50)
        orbit = rough_ellipse(4.95, 3.05, center=earth_center, color=TEAL, stroke_width=4.5, seed=51)
        satellite = Dot(earth_center + RIGHT * 2.12 + UP * 0.68, radius=0.11, color=GOLD)
        trails = VGroup(*[
            Dot(earth_center + RIGHT * x + UP * y, radius=0.04, color=GOLD).set_opacity(opacity)
            for x, y, opacity in ((1.82, 0.92, 0.25), (1.97, 0.82, 0.45), (2.08, 0.74, 0.7))
        ])
        takeaway = sticky_note(
            "a fall that keeps missing",
            RIGHT * 1.93 + DOWN * 1.65,
            width=3.05,
            height=1.08,
            color=TEAL,
            seed=52,
            size=25,
        )
        no_thruster = VGroup(
            rough_line(RIGHT * 1.35 + UP * 1.85, RIGHT * 2.55 + UP * 1.85, color=MUTED, width=3, seed=53),
            hand_label("no constant thrust", RIGHT * 1.95 + UP * 2.15, color=MUTED, size=20, max_width=2.25),
        )
        content = VGroup(orbit, earth, satellite, trails, takeaway, no_thruster)
        cue_targets = [orbit, satellite, takeaway, no_thruster]
        highlight = orbit[0]
    return visual_board(stage, content, cue_targets=cue_targets, highlight_path=highlight)


def _loss_curve(center=ORIGIN, width=5.6, height=2.8, color=TEAL, seed=60):
    points = []
    for index in range(41):
        x = -1.0 + 2.0 * index / 40
        points.append(center + np.array([x * width / 2, (x * x - 0.6) * height / 2, 0.0]))
    return rough_path(points, color=color, width=4.5, seed=seed)


def _loss_axes(center=ORIGIN, width=6.0, height=3.4, seed=61):
    return VGroup(
        rough_arrow(center + LEFT * width / 2 + DOWN * height * 0.28, center + RIGHT * width / 2 + DOWN * height * 0.28, color=MUTED, width=2.5, seed=seed),
        rough_arrow(center + DOWN * height * 0.42, center + UP * height * 0.55, color=MUTED, width=2.5, seed=seed + 1),
    ).set_opacity(0.55)


def gradient_descent(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    cue_targets = []
    highlight = None
    if stage == 0:
        left = rough_rect(3.15, 3.5, center=LEFT * 1.75, color=CORAL, seed=61, fill_color=PANEL, fill_opacity=0.3)
        right = rough_rect(3.15, 3.5, center=RIGHT * 1.75, color=TEAL, seed=62, fill_color=PANEL, fill_opacity=0.3)
        target = hand_label("target:  10", LEFT * 1.75 + UP * 0.62, color=CHALK, size=27, max_width=2.3)
        prediction = hand_label("model:  17", LEFT * 1.75, color=GOLD, size=27, max_width=2.3)
        gap = rough_arrow(LEFT * 2.48 + DOWN * 0.6, LEFT * 1.03 + DOWN * 0.6, color=CORAL, width=4, seed=63)
        gap_text = hand_label("the gap = loss", LEFT * 1.75 + DOWN * 1.14, color=CORAL, size=23, max_width=2.4, font=MARKER_FONT)
        curve = _loss_curve(RIGHT * 1.75 + DOWN * 0.22, width=2.55, height=1.8, seed=64)
        point = Dot(RIGHT * 0.92 + UP * 0.3, radius=0.1, color=GOLD)
        question = hand_label("how wrong?", RIGHT * 1.75 + UP * 1.25, color=TEAL, size=25, max_width=2.1, font=MARKER_FONT)
        content = VGroup(left, right, target, prediction, gap, gap_text, curve, point, question)
        cue_targets = [target, prediction, gap, curve]
        highlight = curve[0]
    elif stage == 1:
        axes = _loss_axes(DOWN * 0.15, seed=70)
        curve = _loss_curve(DOWN * 0.15, seed=72)
        point = Dot(LEFT * 2.12 + UP * 0.95, radius=0.105, color=GOLD)
        tangent = rough_line(LEFT * 2.78 + UP * 1.68, LEFT * 1.08 + DOWN * 0.02, color=CORAL, width=4, seed=73)
        uphill = rough_arrow(LEFT * 1.9 + UP * 0.75, LEFT * 2.62 + UP * 1.48, color=CORAL, width=4, seed=74)
        downhill = rough_arrow(LEFT * 1.9 + UP * 0.65, LEFT * 1.05 + DOWN * 0.05, color=GOLD, width=4, seed=75)
        notes = VGroup(
            sticky_note("gradient points uphill", RIGHT * 1.86 + UP * 1.85, width=3.1, color=CORAL, seed=76),
            sticky_note("we step the other way", RIGHT * 1.86 + DOWN * 1.63, width=3.1, color=GOLD, seed=77),
        )
        content = VGroup(axes, curve, point, tangent, uphill, downhill, notes)
        cue_targets = [uphill, tangent, downhill, notes]
        highlight = curve[0]
    elif stage == 2:
        axes = _loss_axes(DOWN * 0.15, seed=80)
        curve = _loss_curve(DOWN * 0.15, seed=82)
        positions = [
            LEFT * 2.35 + UP * 1.18,
            LEFT * 1.42 + UP * 0.10,
            LEFT * 0.68 + DOWN * 0.42,
            LEFT * 0.05 + DOWN * 0.64,
        ]
        dots = VGroup()
        steps = VGroup()
        numbers = VGroup()
        for index, position in enumerate(positions):
            dot = Dot(position, radius=0.10, color=(CORAL, GOLD, TEAL, CHALK)[index])
            dots.add(dot)
            numbers.add(hand_label(str(index + 1), position + UP * 0.34, color=(CORAL, GOLD, TEAL, CHALK)[index], size=18, max_width=0.3))
            if index < len(positions) - 1:
                steps.add(rough_arrow(position, positions[index + 1], color=GOLD, width=3.5, seed=83 + index))
        loop_note = sticky_note("measure → step → measure", RIGHT * 1.85 + UP * 1.62, width=3.35, color=TEAL, seed=88)
        recalc = hand_label("recalculate here", RIGHT * 1.88 + DOWN * 1.45, color=MUTED, size=22, max_width=2.5)
        content = VGroup(axes, curve, steps, dots, numbers, loop_note, recalc)
        cue_targets = [dots[0], steps[0], dots[2], loop_note]
        highlight = curve[0]
    elif stage == 3:
        cards = VGroup()
        labels = (("tiny", CORAL), ("useful", TEAL), ("too big", GOLD))
        for index, (label, color) in enumerate(labels):
            center = LEFT * 2.35 + RIGHT * index * 2.35
            frame = rough_rect(2.08, 3.72, center=center, color=color, seed=90 + index, fill_color=PANEL, fill_opacity=0.30)
            curve = _loss_curve(center + DOWN * 0.25, width=1.65, height=1.35, color=color, seed=94 + index)
            title = hand_label(label, center + UP * 1.42, color=color, size=25, max_width=1.6, font=MARKER_FONT)
            if index == 0:
                step = rough_arrow(center + LEFT * 0.63 + UP * 0.32, center + LEFT * 0.31 + DOWN * 0.06, color=color, width=3, seed=98)
            elif index == 1:
                step = rough_arrow(center + LEFT * 0.62 + UP * 0.32, center + RIGHT * 0.08 + DOWN * 0.52, color=color, width=3, seed=99)
            else:
                step = rough_arrow(center + LEFT * 0.62 + UP * 0.32, center + RIGHT * 0.75 + UP * 0.22, color=color, width=3, seed=100)
            cards.add(VGroup(frame, curve, title, step))
        note = sticky_note("learning rate = step size", DOWN * 2.45, width=3.45, color=GOLD, seed=101)
        content = VGroup(cards, note)
        cue_targets = [cards[0], cards[1], cards[2], note]
        highlight = cards[1][1][0]
    else:
        axes = _loss_axes(LEFT * 0.55 + DOWN * 0.15, width=5.1, seed=110)
        curve = _loss_curve(LEFT * 0.55 + DOWN * 0.15, width=4.75, seed=112)
        positions = [
            LEFT * 2.45 + UP * 1.04,
            LEFT * 1.55 + UP * 0.02,
            LEFT * 0.78 + DOWN * 0.48,
            LEFT * 0.12 + DOWN * 0.68,
        ]
        dots = VGroup(*[Dot(position, radius=0.095, color=color) for position, color in zip(positions, (CORAL, GOLD, TEAL, CHALK))])
        steps = VGroup(*[
            rough_arrow(positions[index], positions[index + 1], color=GOLD, width=3.2, seed=114 + index)
            for index in range(len(positions) - 1)
        ])
        cycle = sticky_note("repeat until the loss stops improving", RIGHT * 2.12 + UP * 1.25, width=3.0, height=1.28, color=TEAL, seed=118, size=22)
        boundary = sticky_note("not every surface has one perfect bottom", RIGHT * 2.12 + DOWN * 1.48, width=3.0, height=1.28, color=VIOLET, seed=119, size=21)
        content = VGroup(axes, curve, steps, dots, cycle, boundary)
        cue_targets = [steps, dots[-1], cycle, boundary]
        highlight = curve[0]
    return visual_board(stage, content, cue_targets=cue_targets, highlight_path=highlight)


def _token_card(value, center, color=TEAL, width=1.25, seed=1, size=22):
    frame = rough_rect(width, 0.68, center=center, color=color, stroke_width=3, seed=seed, fill_color=PANEL, fill_opacity=0.48)
    text = fitted_text(value, max_width=width - 0.18, size=size, color=CHALK, font=HAND_FONT).move_to(center)
    return VGroup(frame, text)


def attention_flow(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    cue_targets = []
    highlight = None
    if stage == 0:
        token = _token_card("bank", UP * 1.75, color=GOLD, width=1.6, seed=120, size=27)
        labels = (("Q", CORAL, LEFT * 2.15), ("K", TEAL, ORIGIN), ("V", VIOLET, RIGHT * 2.15))
        projections = VGroup()
        arrows = VGroup()
        for index, (label, color, x_shift) in enumerate(labels):
            center = x_shift + DOWN * 0.65
            card = _token_card(label, center, color=color, width=1.15, seed=121 + index, size=30)
            detail = hand_label(
                ("asks", "matches", "carries")[index],
                center + DOWN * 0.78,
                color=color,
                size=20,
                max_width=1.3,
                font=MARKER_FONT,
            )
            arrow = rough_arrow(token.get_bottom(), center + UP * 0.36, color=color, width=3.5, seed=125 + index)
            projections.add(VGroup(card, detail))
            arrows.add(arrow)
        note = sticky_note("one token → three roles", DOWN * 2.34, width=3.4, color=GOLD, seed=129)
        content = VGroup(token, arrows, projections, note)
        cue_targets = [token, projections[0], projections[1], projections[2], note]
        highlight = arrows[1][0][0]
    elif stage == 1:
        query = _token_card("QUERY\nbank", LEFT * 2.42 + UP * 0.52, color=CORAL, width=1.75, seed=130, size=20)
        key_values = (("the", "0.1", MUTED), ("was", "0.6", GOLD), ("steep", "0.9", CORAL))
        keys = VGroup()
        arrows = VGroup()
        for index, (word, score, color) in enumerate(key_values):
            center = RIGHT * 1.65 + UP * (1.45 - index * 1.4)
            card = _token_card(word, center, color=color, width=1.55, seed=131 + index)
            score_text = hand_label(score, center + RIGHT * 1.05, color=color, size=24, max_width=0.7, font=MARKER_FONT)
            arrow = rough_arrow(query.get_right(), center + LEFT * 0.82, color=color, width=2.5 + index, seed=135 + index)
            keys.add(VGroup(card, score_text))
            arrows.add(arrow)
        note = sticky_note("compare Q with every K", LEFT * 1.48 + DOWN * 1.72, width=3.15, color=CORAL, seed=139)
        content = VGroup(query, arrows, keys, note)
        cue_targets = [query, keys[0], keys[1], keys[2], note]
        highlight = arrows[-1][0][0]
    elif stage == 2:
        scores = VGroup(
            hand_label("0.1", LEFT * 2.72 + UP * 1.28, color=MUTED, size=25, max_width=0.7),
            hand_label("0.6", LEFT * 2.72, color=GOLD, size=25, max_width=0.7),
            hand_label("0.9", LEFT * 2.72 + DOWN * 1.28, color=CORAL, size=25, max_width=0.7),
        )
        funnel = rough_path(
            [
                LEFT * 1.95 + UP * 1.7,
                LEFT * 0.75 + UP * 0.55,
                LEFT * 0.75 + DOWN * 0.55,
                LEFT * 1.95 + DOWN * 1.7,
            ],
            color=TEAL,
            width=4,
            seed=140,
        )
        softmax = hand_label("softmax", LEFT * 1.32, color=TEAL, size=22, max_width=1.35, font=MARKER_FONT)
        bar_specs = (("10%", 0.65, MUTED), ("35%", 1.45, GOLD), ("55%", 2.25, CORAL))
        bars = VGroup()
        for index, (label, width, color) in enumerate(bar_specs):
            y = 1.3 - index * 1.3
            stroke = rough_line(RIGHT * 0.35 + UP * y, RIGHT * (0.35 + width) + UP * y, color=color, width=12, seed=143 + index)
            text = hand_label(label, RIGHT * 3.05 + UP * y, color=color, size=22, max_width=0.75)
            bars.add(VGroup(stroke, text))
        note = sticky_note("scores become weights", DOWN * 2.33, width=3.3, color=TEAL, seed=147)
        content = VGroup(scores, funnel, softmax, bars, note)
        cue_targets = [scores, funnel, bars[0], bars[2], note]
        highlight = bars[2][0][0]
    elif stage == 3:
        values = VGroup(
            _token_card("V₁", LEFT * 2.7 + UP * 1.35, color=MUTED, width=1.1, seed=150, size=25),
            _token_card("V₂", LEFT * 2.7, color=GOLD, width=1.1, seed=151, size=25),
            _token_card("V₃", LEFT * 2.7 + DOWN * 1.35, color=CORAL, width=1.1, seed=152, size=25),
        )
        arrows = VGroup()
        for index, value in enumerate(values):
            arrows.add(rough_arrow(value.get_right(), LEFT * 0.18 + UP * (0.28 - index * 0.28), color=(MUTED, GOLD, CORAL)[index], width=3 + index, seed=154 + index))
        mixer = rough_circle(0.62, center=RIGHT * 0.38, color=TEAL, stroke_width=4, seed=158, fill_color=TEAL, fill_opacity=0.08)
        sigma = hand_label("Σ", RIGHT * 0.38, color=TEAL, size=38, max_width=0.65, font=MARKER_FONT)
        output = _token_card("bank\n+ context", RIGHT * 2.5, color=TEAL, width=1.9, seed=159, size=21)
        output_arrow = rough_arrow(RIGHT * 1.02, output.get_left(), color=TEAL, width=4, seed=160)
        note = sticky_note("weighted values mix", DOWN * 2.32, width=3.2, color=TEAL, seed=161)
        content = VGroup(values, arrows, mixer, sigma, output_arrow, output, note)
        cue_targets = [values, arrows, mixer, output, note]
        highlight = output_arrow[0][0]
    else:
        panels = VGroup()
        colors = (CORAL, GOLD, TEAL)
        link_pairs = ((0, 2), (1, 3), (0, 3))
        for index in range(3):
            center = LEFT * 2.38 + RIGHT * index * 2.38
            frame = rough_rect(2.08, 3.75, center=center, color=colors[index], seed=170 + index, fill_color=PANEL, fill_opacity=0.30)
            title = hand_label(f"HEAD {index + 1}", center + UP * 1.45, color=colors[index], size=21, max_width=1.5, font=MARKER_FONT)
            token_dots = VGroup(*[
                rough_circle(
                    0.16,
                    center=center + LEFT * 0.66 + RIGHT * dot_index * 0.44 + DOWN * 0.12,
                    color=CHALK,
                    stroke_width=2,
                    seed=174 + index * 4 + dot_index,
                    fill_color=CHALK,
                    fill_opacity=0.16,
                )
                for dot_index in range(4)
            ])
            start_index, end_index = link_pairs[index]
            link = rough_arrow(
                token_dots[start_index].get_center() + UP * 0.08,
                token_dots[end_index].get_center() + UP * 0.08,
                color=colors[index],
                width=3,
                seed=190 + index,
            )
            meaning = hand_label(
                ("syntax", "position", "meaning")[index],
                center + DOWN * 1.12,
                color=colors[index],
                size=20,
                max_width=1.55,
            )
            panels.add(VGroup(frame, title, token_dots, link, meaning))
        combine = sticky_note("different links → richer context", DOWN * 2.45, width=3.75, color=VIOLET, seed=195)
        content = VGroup(panels, combine)
        cue_targets = [panels[0], panels[1], panels[2], combine]
        highlight = panels[2][3][0][0]
    return visual_board(stage, content, cue_targets=cue_targets, highlight_path=highlight)


def vector_transform(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    origin = Dot(LEFT * 1.8 + DOWN * 0.2, color=CHALK)
    down = rough_arrow(origin.get_center(), origin.get_center() + DOWN * 1.8, color=CORAL, seed=210)
    side = rough_arrow(origin.get_center(), origin.get_center() + RIGHT * 2.7, color=GOLD, seed=211)
    curve = rough_path(
        [origin.get_center(), LEFT * 0.8 + DOWN * 0.7, RIGHT * 0.5 + DOWN * 1.25, RIGHT * 2.25 + DOWN * 1.45],
        color=TEAL,
        width=5,
        seed=212,
    )
    content = VGroup(origin, down, side, curve, sticky_note("vectors combine", UP * 1.8, color=TEAL, seed=213))
    return visual_board(stage, content, cue_targets=[down, side, curve], highlight_path=curve[0])


def model_cards(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    cards = VGroup()
    for index, (name, color) in enumerate((("SOL", CORAL), ("TERRA", GOLD), ("LUNA", TEAL))):
        center = LEFT * 2.3 + RIGHT * index * 2.3
        cards.add(VGroup(
            rough_rect(1.95, 3.2, center=center, color=color, seed=220 + index, fill_color=PANEL, fill_opacity=0.32),
            hand_label(name, center, color=color, size=28, max_width=1.5, font=MARKER_FONT),
        ))
    return visual_board(stage, cards, cue_targets=list(cards))


def timeline(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    line = rough_line(LEFT * 3.0, RIGHT * 3.0, color=TEAL, width=4, seed=230)
    dots = VGroup(*[rough_circle(0.13, center=LEFT * 3.0 + RIGHT * index * 1.5, color=GOLD, seed=231 + index, fill_color=GOLD, fill_opacity=0.55) for index in range(5)])
    content = VGroup(line, dots)
    return visual_board(stage, content, cue_targets=list(dots), highlight_path=line[0])


def comparison_grid(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    cards = VGroup(*[
        rough_rect(2.75, 1.55, center=LEFT * 1.5 + RIGHT * (index % 2) * 3.0 + UP * 1.0 + DOWN * (index // 2) * 2.0, color=(CORAL, GOLD, TEAL, VIOLET)[index], seed=240 + index, fill_color=PANEL, fill_opacity=0.3)
        for index in range(4)
    ])
    return visual_board(stage, cards, cue_targets=list(cards))


def tokens_context(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    tokens = VGroup(*[
        _token_card(str(index + 1), LEFT * 2.25 + RIGHT * (index % 4) * 1.5 + UP * 1.0 + DOWN * (index // 4) * 1.05, color=(TEAL, GOLD, CORAL)[index % 3], width=1.1, seed=250 + index)
        for index in range(12)
    ])
    return visual_board(stage, tokens, cue_targets=list(tokens))


def eval_bars(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    bars = VGroup(*[
        rough_line(LEFT * 2.65 + UP * (1.25 - index * 1.15), LEFT * 2.65 + RIGHT * width + UP * (1.25 - index * 1.15), color=(CORAL, GOLD, TEAL)[index], width=12, seed=270 + index)
        for index, width in enumerate((2.1, 3.4, 4.8))
    ])
    return visual_board(stage, bars, cue_targets=list(bars), highlight_path=bars[-1][0])


def agent_loop(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    nodes = VGroup(*[
        rough_circle(0.48, center=LEFT * 1.3 + RIGHT * (index % 2) * 2.6 + UP * 1.15 + DOWN * (index // 2) * 2.3, color=(CORAL, GOLD, TEAL, VIOLET)[index], seed=280 + index, fill_color=PANEL, fill_opacity=0.5)
        for index in range(4)
    ])
    links = VGroup(
        rough_arrow(nodes[0].get_center(), nodes[1].get_center(), color=GOLD, seed=285),
        rough_arrow(nodes[1].get_center(), nodes[3].get_center(), color=TEAL, seed=286),
        rough_arrow(nodes[3].get_center(), nodes[2].get_center(), color=VIOLET, seed=287),
        rough_arrow(nodes[2].get_center(), nodes[0].get_center(), color=CORAL, seed=288),
    )
    content = VGroup(nodes, links)
    return visual_board(stage, content, cue_targets=list(nodes), highlight_path=links[0][0][0])


def claim_callout(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    note = sticky_note(item.get("body", "source-backed claim"), ORIGIN, width=5.8, height=2.1, color=TEAL, seed=290, size=29)
    return visual_board(stage, note, cue_targets=[note])


def routing_diagram(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    center = rough_circle(0.48, center=LEFT * 1.65, color=GOLD, seed=300, fill_color=GOLD, fill_opacity=0.18)
    targets = VGroup(*[
        rough_rect(1.65, 0.75, center=RIGHT * 1.65 + UP * (1.1 - index * 1.1), color=(CORAL, TEAL, VIOLET)[index], seed=301 + index, fill_color=PANEL, fill_opacity=0.4)
        for index in range(3)
    ])
    arrows = VGroup(*[rough_arrow(center.get_center(), target.get_center(), color=TEAL, width=3, seed=305 + index) for index, target in enumerate(targets)])
    content = VGroup(center, arrows, targets)
    return visual_board(stage, content, cue_targets=list(targets), highlight_path=arrows[1][0][0])


def before_after(item):
    stage = int(item.get("params", {}).get("beat_index", 0))
    left = rough_rect(2.65, 2.5, center=LEFT * 1.75, color=MUTED, seed=310, fill_color=PANEL, fill_opacity=0.35)
    right = rough_rect(2.65, 2.5, center=RIGHT * 1.75, color=TEAL, seed=311, fill_color=PANEL, fill_opacity=0.35)
    arrow = rough_arrow(LEFT * 0.3, RIGHT * 0.3, color=GOLD, width=4, seed=312)
    content = VGroup(left, arrow, right)
    return visual_board(stage, content, cue_targets=[left, arrow, right], highlight_path=arrow[0][0])


PRIMITIVES = {
    "model_cards": model_cards,
    "timeline": timeline,
    "comparison_grid": comparison_grid,
    "tokens_context": tokens_context,
    "eval_bars": eval_bars,
    "agent_loop": agent_loop,
    "claim_callout": claim_callout,
    "routing_diagram": routing_diagram,
    "before_after": before_after,
    "orbit_trace": orbit_trace,
    "vector_transform": vector_transform,
    "gradient_descent": gradient_descent,
    "attention_flow": attention_flow,
}


def chalk_dust():
    dust = VGroup()
    for index in range(96):
        x = -4.35 + ((index * 1.731) % 8.7)
        y = -7.85 + ((index * 2.417) % 15.7)
        radius = 0.006 + (index % 3) * 0.003
        dust.add(Dot(np.array([x, y, 0.0]), radius=radius, color=CHALK).set_opacity(0.025 + (index % 5) * 0.008))
    return dust


def cue_animation(scene, visual, cue_index, run_time):
    animations = []
    targets = getattr(visual, "cue_targets", [])
    if targets:
        target = targets[cue_index % len(targets)]
        animations.append(Circumscribe(target, color=(GOLD, TEAL, CORAL)[cue_index % 3], fade_out=True, time_width=0.45))
    highlight = getattr(visual, "highlight_path", None)
    if highlight is not None and cue_index % 2:
        flash = highlight.copy().set_stroke((GOLD, TEAL, CORAL)[cue_index % 3], width=10, opacity=0.92)
        animations.append(ShowPassingFlash(flash, time_width=0.32))
    if not animations:
        animations.append(Indicate(visual, color=GOLD, scale_factor=1.015))
    scene.play(AnimationGroup(*animations, lag_ratio=0.05), run_time=run_time)


class ContentMaxxerScene(Scene):
    def construct(self):
        self.camera.background_color = SPEC["background"]
        self.add(chalk_dust())
        current_title = None
        current_visual = None
        current_badge = None
        current_caption = None

        caption_center = DOWN * 4.68
        caption_panel = rough_rect(
            7.48,
            1.28,
            center=caption_center,
            color=BOARD_EDGE,
            stroke_width=2.6,
            seed=500,
            fill_color=PANEL_2,
            fill_opacity=0.92,
        )
        self.add(caption_panel)

        for beat_index, item in enumerate(SPEC["primitives"]):
            beat_origin = self.time
            duration = max(0.2, item["duration_seconds"])
            title_text = wrapped_text(
                item["title"],
                size=45,
                weight=BOLD,
                font=MARKER_FONT,
            ).move_to(UP * 5.35)
            title_underline = rough_line(
                title_text.get_corner(DL) + DOWN * 0.10,
                title_text.get_corner(DR) + DOWN * 0.10,
                color=GOLD,
                width=3.2,
                seed=510 + beat_index,
            )
            title = VGroup(title_text, title_underline)
            visual = PRIMITIVES.get(item["kind"], claim_callout)(item).move_to(UP * 0.42)
            badge = source_badge(item["source_label"])
            captions = item.get("params", {}).get("captions", [])
            first_caption_text = captions[0]["text"] if captions else item["body"]
            caption = wrapped_text(
                first_caption_text,
                max_width=6.75,
                max_height=0.92,
                chars=25,
                lines=2,
                size=34,
                weight=BOLD,
                font=HAND_FONT,
            ).move_to(caption_center)

            if current_title is None:
                self.play(
                    FadeIn(title, shift=UP * 0.10),
                    FadeIn(badge),
                    FadeIn(caption),
                    run_time=min(0.42, duration * 0.09),
                )
                self.play(
                    FadeIn(visual[0]),
                    LaggedStart(*[Create(part) for part in visual[1:]], lag_ratio=0.10),
                    run_time=min(1.0, duration * 0.19),
                )
            else:
                self.remove(current_caption)
                self.add(caption)
                self.play(
                    FadeOut(current_title, shift=UP * 0.08),
                    FadeOut(current_visual, shift=LEFT * 0.10),
                    FadeOut(current_badge),
                    run_time=min(0.24, duration * 0.04),
                )
                self.play(
                    FadeIn(title, shift=UP * 0.08),
                    FadeIn(badge),
                    FadeIn(visual[0]),
                    LaggedStart(
                        *[FadeIn(part, shift=UP * 0.05) for part in visual[1:]],
                        lag_ratio=0.07,
                    ),
                    run_time=min(0.72, duration * 0.13),
                )

            current_title = title
            current_visual = visual
            current_badge = badge
            current_caption = caption

            for caption_index, cue in enumerate(captions[1:], start=1):
                target_time = beat_origin + cue["start_seconds"]
                if self.time < target_time:
                    self.wait(target_time - self.time)
                replacement = wrapped_text(
                    cue["text"],
                    max_width=6.75,
                    max_height=0.92,
                    chars=25,
                    lines=2,
                    size=34,
                    weight=BOLD,
                    font=HAND_FONT,
                ).move_to(caption_center)
                self.remove(current_caption)
                self.add(replacement)
                current_caption = replacement
                cue_animation(
                    self,
                    current_visual,
                    caption_index,
                    min(0.26, max(0.14, cue["end_seconds"] - cue["start_seconds"])),
                )

            beat_end = beat_origin + duration
            if self.time < beat_end:
                self.wait(beat_end - self.time)

        if current_title is not None:
            self.play(
                FadeOut(VGroup(current_title, current_visual, current_badge, current_caption, caption_panel)),
                run_time=0.42,
            )
'''


STYLE_EXPERIMENT_SCENE_LIBRARY = r'''

STYLE = SPEC["animation_style"]
STORY = SPEC.get("story", {})
STORY_STAGES = STORY.get("stages", [])


def palette():
    if STYLE == "hand_drawn":
        return {
            "ink": "#F7F3E8", "muted": "#8FA6B8", "a": "#67E8D4", "b": "#FF718A",
            "c": "#F9C74F", "paper": "#07111F", "font": "Chalkboard SE",
        }
    if STYLE == "whiteboard":
        return {
            "ink": "#20252B", "muted": "#6B7280", "a": "#247BA0", "b": "#E45756",
            "c": "#E3A008", "paper": "#F7F3E8", "font": "Chalkboard SE",
        }
    if STYLE == "warm_papyrus":
        return {
            "ink": "#3C2F2A", "muted": "#7B654F", "a": "#B8543E", "b": "#26736B",
            "c": "#C08A2D", "paper": "#E7D1A5", "font": "Baskerville",
        }
    if STYLE == "future_minimal":
        return {
            "ink": "#EEF7FF", "muted": "#71859B", "a": "#42F5D7", "b": "#FF4FA3",
            "c": "#C6FF4A", "paper": "#050914", "font": "Avenir Next",
        }
    return {
        "ink": "#FFF7E8", "muted": "#A89CA8", "a": "#FF5D5D", "b": "#59D8C6",
        "c": "#F6C95D", "paper": "#111018", "font": "Avenir Next",
    }


P = palette()


def fit_text(value, max_width=7.2, size=46, color=None, weight=NORMAL, font=None):
    text = Text(
        value,
        font=font or P["font"],
        font_size=size,
        color=color or P["ink"],
        weight=weight,
        line_spacing=0.82,
    )
    if text.width > max_width:
        text.scale_to_fit_width(max_width)
    return text


def wrap_text(value, max_width=7.2, max_height=1.35, chars=24, lines=2, size=44, color=None, weight=BOLD):
    wrapped = textwrap.wrap(value, width=chars, break_long_words=False, break_on_hyphens=False)
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] = wrapped[-1].rstrip(" .,;:") + "…"
    text = fit_text(
        "\n".join(wrapped),
        max_width=max_width,
        size=size,
        color=color,
        weight=weight,
    )
    if text.height > max_height:
        text.scale_to_fit_height(max_height)
    return text


def complete_wrap_text(value, max_width=7.2, max_height=1.45, chars=30, lines=3, size=46, color=None, weight=BOLD):
    compact = " ".join(str(value).split())
    target_width = max(12, int(chars))
    wrapped = textwrap.wrap(
        compact,
        width=target_width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    while len(wrapped) > lines:
        target_width += 2
        wrapped = textwrap.wrap(
            compact,
            width=target_width,
            break_long_words=False,
            break_on_hyphens=False,
        )
    text = fit_text(
        "\n".join(wrapped),
        max_width=max_width,
        size=size,
        color=color,
        weight=weight,
    )
    if text.height > max_height:
        text.scale_to_fit_height(max_height)
    return text


def ink_path(points, color=None, width=4, seed=1, closed=False, opacity=1.0):
    raw = [np.array(point, dtype=float) for point in points]
    strokes = VGroup()
    passes = 3 if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"} else 1
    for pass_index in range(passes):
        jittered = []
        for index, point in enumerate(raw):
            amount = 0.012 + pass_index * 0.006
            phase = (index + 1) * (seed + pass_index * 5.17)
            jittered.append(
                point
                + np.array(
                    [
                        amount * np.sin(phase * 1.71),
                        amount * np.cos(phase * 1.31),
                        0.0,
                    ]
                )
            )
        if closed:
            jittered.append(jittered[0])
        line = VMobject()
        if len(jittered) > 4:
            line.set_points_smoothly(jittered)
        else:
            line.set_points_as_corners(jittered)
        line.set_stroke(
            color or P["ink"],
            width=max(1.0, width - pass_index * 0.75),
            opacity=opacity * (0.86 if pass_index == 0 else 0.24),
        )
        strokes.add(line)
    return strokes


def ink_line(start, end, color=None, width=4, seed=1, opacity=1.0):
    start = np.array(start, dtype=float)
    end = np.array(end, dtype=float)
    return ink_path(
        [interpolate(start, end, alpha) for alpha in (0, 0.23, 0.51, 0.77, 1)],
        color=color,
        width=width,
        seed=seed,
        opacity=opacity,
    )


def ink_circle(center, radius, color=None, width=4, seed=1, opacity=1.0):
    points = []
    for index in range(41):
        angle = TAU * index / 40
        points.append(
            np.array(
                [
                    center[0] + radius * np.cos(angle),
                    center[1] + radius * np.sin(angle),
                    0,
                ]
            )
        )
    return ink_path(points, color=color, width=width, seed=seed, closed=True, opacity=opacity)


def ink_arrow(start, end, color=None, width=4, seed=1, opacity=1.0):
    color = color or P["ink"]
    start = np.array(start, dtype=float)
    end = np.array(end, dtype=float)
    shaft = ink_line(start, end, color=color, width=width, seed=seed, opacity=opacity)
    direction = end - start
    angle = np.arctan2(direction[1], direction[0])
    tip = Triangle(fill_color=color, fill_opacity=opacity, stroke_opacity=0).scale(0.11)
    tip.rotate(angle - PI / 2).move_to(end)
    return VGroup(shaft, tip)


def tiny_label(value, point, color=None, size=23, rotation=0):
    label = fit_text(value, max_width=2.3, size=size, color=color or P["muted"], weight=BOLD)
    label.move_to(point).rotate(rotation)
    return label


def source_name(item):
    body = item.get("body", "") + " " + item.get("title", "")
    if "NVIDIA" in body:
        return "NVIDIA OPEN-WEIGHTS LETTER"
    if "Amodei" in body or "Dario" in body:
        return "DARIO AMODEI / ANTHROPIC"
    return str(item.get("source_label", "PRIMARY SOURCE")).upper()


def background_texture():
    texture = VGroup()
    if STORY.get("kind") in {
        "elastic_llm_nesting",
        "lecun_world_model_bet",
        "technology_adolescence",
    }:
        # This story deliberately has no generated grain, grid, dust, or
        # ambient particles. Motion should communicate a new idea, not noise.
        return texture
    if STYLE == "hand_drawn":
        for index in range(88):
            x = -4.25 + ((index * 1.731) % 8.5)
            y = -7.0 + ((index * 2.417) % 14.0)
            radius = 0.006 + (index % 3) * 0.003
            texture.add(
                Dot([x, y, 0], radius=radius, color=P["ink"]).set_opacity(
                    0.025 + (index % 5) * 0.008
                )
            )
        for x in np.linspace(-4.0, 4.0, 9):
            texture.add(
                Line(
                    [x, -6.7, 0],
                    [x, 6.45, 0],
                    color="#29445C",
                    stroke_width=1,
                    stroke_opacity=0.055,
                )
            )
        for y in np.linspace(-6.7, 6.45, 14):
            texture.add(
                Line(
                    [-4.0, y, 0],
                    [4.0, y, 0],
                    color="#29445C",
                    stroke_width=1,
                    stroke_opacity=0.045,
                )
            )
        texture.add(
            ink_path(
                [[-4.05, -6.7, 0], [-4.05, 6.45, 0], [4.05, 6.45, 0], [4.05, -6.7, 0]],
                color="#29445C",
                width=2,
                seed=705,
                opacity=0.42,
            )
        )
    elif STYLE == "whiteboard":
        for index, y in enumerate(np.linspace(-7.1, 6.9, 36)):
            line = Line(LEFT * 4.4 + UP * y, RIGHT * 4.4 + UP * y)
            line.set_stroke("#85A8C4", width=1, opacity=0.055)
            texture.add(line)
        texture.add(
            ink_path(
                [LEFT * 3.95 + DOWN * 6.6, LEFT * 3.87 + UP * 6.6],
                color="#E45756",
                width=2,
                opacity=0.18,
            )
        )
    elif STYLE == "warm_papyrus":
        for index in range(54):
            y = -7.3 + index * 0.275
            wobble = 0.018 * np.sin(index * 1.7)
            texture.add(
                Line(
                    LEFT * 4.5 + UP * (y + wobble),
                    RIGHT * 4.5 + UP * (y - wobble),
                    stroke_color="#694C35",
                    stroke_width=1,
                    stroke_opacity=0.06 + 0.02 * (index % 3 == 0),
                )
            )
        for x, y, r in ((-3.5, 5.6, 0.08), (3.3, -4.9, 0.06), (2.9, 5.9, 0.04), (-2.8, -5.8, 0.05)):
            texture.add(Circle(radius=r, fill_color="#8A5B3C", fill_opacity=0.11, stroke_opacity=0).move_to([x, y, 0]))
    elif STYLE == "future_minimal":
        for x in np.linspace(-4.3, 4.3, 14):
            texture.add(Line([x, -7.2, 0], [x, 7.2, 0], color=P["a"], stroke_width=1, stroke_opacity=0.045))
        for y in np.linspace(-7.2, 7.2, 24):
            texture.add(Line([-4.3, y, 0], [4.3, y, 0], color=P["a"], stroke_width=1, stroke_opacity=0.035))
        texture.add(Line(LEFT * 4.1 + UP * 6.55, RIGHT * 4.1 + UP * 6.55, color=P["a"], stroke_width=2, stroke_opacity=0.35))
    else:
        texture.add(
            Polygon(
                [-4.5, 6.9, 0], [-0.7, 7.2, 0], [-2.5, -7.2, 0], [-4.5, -7.2, 0],
                fill_color="#241622", fill_opacity=0.62, stroke_opacity=0,
            )
        )
        texture.add(
            Polygon(
                [4.5, 6.9, 0], [1.3, 7.2, 0], [2.7, -7.2, 0], [4.5, -7.2, 0],
                fill_color="#102529", fill_opacity=0.58, stroke_opacity=0,
            )
        )
        for index in range(24):
            x = -4.0 + (index * 1.37) % 8.0
            y = -6.7 + (index * 2.11) % 13.4
            texture.add(Dot([x, y, 0], radius=0.018, color=P["c"]).set_opacity(0.22))
    return texture


def whiteboard_visual(stage):
    visual = VGroup()
    center = np.array([0.0, 0.25, 0.0])
    model_sheet = ink_path(
        [
            [-0.92, -0.72, 0],
            [0.62, -0.78, 0],
            [0.94, -0.48, 0],
            [0.86, 1.18, 0],
            [-0.78, 1.10, 0],
            [-1.0, 0.78, 0],
        ],
        color=P["a"],
        width=6,
        seed=4,
        closed=True,
    )
    folded_corner = ink_path(
        [[0.62, -0.78, 0], [0.58, -0.45, 0], [0.94, -0.48, 0]],
        color=P["a"],
        width=3,
        seed=7,
    )
    download_mark = VGroup(
        ink_line([0, 0.9, 0], [0, 0.48, 0], color=P["c"], width=4, seed=8),
        ink_path(
            [[-0.22, 0.62, 0], [0, 0.42, 0], [0.22, 0.62, 0]],
            color=P["c"],
            width=4,
            seed=9,
        ),
    )
    visual.add(
        semantic_part(
            "open_weights_core",
            model_sheet,
            folded_corner,
            download_mark,
            fit_text("OPEN\nWEIGHTS", max_width=1.45, size=29, color=P["ink"], weight=BOLD).move_to([0, 0.02, 0]),
        )
    )
    visual.add(
        semantic_part(
            "framing",
            tiny_label("not open vs closed", [0, 2.15, 0], color=P["b"], size=27, rotation=-0.025),
            ink_line([-1.55, 1.95, 0], [1.52, 1.93, 0], color=P["b"], width=5, seed=12),
        )
    )
    if stage >= 1:
        access_center = np.array([-2.72, 1.0, 0])
        compete_center = np.array([0, -1.78, 0])
        control_center = np.array([2.72, 1.0, 0])
        access_doodle = VGroup(
            ink_path(
                [
                    access_center + [-0.34, -0.34, 0],
                    access_center + [-0.34, 0.34, 0],
                    access_center + [0.24, 0.34, 0],
                    access_center + [0.24, -0.34, 0],
                ],
                color=P["a"],
                width=4,
                seed=21,
            ),
            ink_arrow(
                access_center + [-0.05, 0, 0],
                access_center + [-0.62, 0, 0],
                color=P["a"],
                width=4,
                seed=22,
            ),
            tiny_label("ACCESS", access_center + DOWN * 0.72, color=P["a"], size=22),
        )
        compete_doodle = VGroup(
            ink_arrow(
                compete_center + [-0.58, -0.24, 0],
                compete_center + [0.58, 0.24, 0],
                color=P["c"],
                width=4,
                seed=24,
            ),
            ink_arrow(
                compete_center + [-0.58, 0.24, 0],
                compete_center + [0.58, -0.24, 0],
                color=P["c"],
                width=4,
                seed=25,
            ),
            tiny_label("COMPETE", compete_center + DOWN * 0.72, color=P["c"], size=22),
        )
        control_doodle = VGroup()
        for index, knob_x in enumerate((-0.18, 0.20, -0.06)):
            y = 1.28 - index * 0.28
            control_doodle.add(
                ink_line(
                    [2.30, y, 0],
                    [3.15, y, 0],
                    color=P["b"],
                    width=3,
                    seed=27 + index,
                ),
                ink_circle(
                    [2.72 + knob_x, y, 0],
                    0.08,
                    color=P["b"],
                    width=3,
                    seed=31 + index,
                ),
            )
        control_doodle.add(
            tiny_label("CONTROL", control_center + DOWN * 0.72, color=P["b"], size=22)
        )
        benefit_parts = [
            ink_path(
                [[-0.82, 0.55, 0], [-1.55, 0.78, 0], [-2.22, 0.98, 0]],
                color=P["a"],
                width=4,
                seed=35,
            ),
            access_doodle,
            ink_path(
                [[-0.10, -0.75, 0], [-0.05, -1.15, 0], [0, -1.36, 0]],
                color=P["c"],
                width=4,
                seed=36,
            ),
            compete_doodle,
            ink_path(
                [[0.82, 0.55, 0], [1.52, 0.77, 0], [2.22, 0.98, 0]],
                color=P["b"],
                width=4,
                seed=37,
            ),
            control_doodle,
        ]
        visual.add(semantic_part("shared_benefits", *benefit_parts))
    if stage >= 2:
        wave = ink_path(
            [[-3.25, -3.0, 0], [-1.8, -2.66, 0], [0, -3.15, 0], [1.8, -2.68, 0], [3.25, -3.0, 0]],
            color=P["b"],
            width=5,
            seed=31,
        )
        escaping_copies = VGroup()
        for index, (x, y, tilt) in enumerate(
            ((-1.55, -2.82, -0.08), (0, -2.97, 0.05), (1.55, -2.78, 0.11))
        ):
            copy = VGroup(
                ink_path(
                    [
                        [x - 0.22, y - 0.26, 0],
                        [x + 0.20, y - 0.24, 0],
                        [x + 0.22, y + 0.26, 0],
                        [x - 0.20, y + 0.23, 0],
                    ],
                    color=P["b"],
                    width=3,
                    seed=42 + index,
                    closed=True,
                ),
                ink_line(
                    [x - 0.12, y + 0.06, 0],
                    [x + 0.12, y + 0.06, 0],
                    color=P["b"],
                    width=2,
                    seed=46 + index,
                ),
            ).rotate(tilt, about_point=[x, y, 0])
            escaping_copies.add(copy)
        irreversible_parts = [wave, escaping_copies]
        if stage == 2:
            irreversible_parts.append(
                tiny_label(
                    "copies escape • no rewind",
                    [0, -3.52, 0],
                    color=P["b"],
                    size=24,
                    rotation=0.02,
                )
            )
        visual.add(semantic_part("irreversibility", *irreversible_parts))
    if stage >= 3:
        beam = ink_line([-2.55, -3.9, 0], [2.55, -3.75, 0], color=P["ink"], width=5, seed=45)
        pivot = Triangle(fill_color=P["muted"], fill_opacity=0.65, stroke_opacity=0).scale(0.34).move_to([0, -4.23, 0])
        visual.add(
            semantic_part(
                "attacker_defender",
                beam,
                pivot,
                tiny_label("DEFENDERS", [-2.25, -3.52, 0], color=P["a"], size=24, rotation=0.02),
                tiny_label("ATTACKERS", [2.22, -3.32, 0], color=P["b"], size=24, rotation=0.02),
                tiny_label("who gains more?", [0, -4.68, 0], color=P["ink"], size=28, rotation=-0.02),
            )
        )
    if stage >= 4:
        response_parts = [
            tiny_label("NOT A BAN", [0, 3.78, 0], color=P["a"], size=29, rotation=-0.025),
            ink_line([-1.05, 3.51, 0], [1.08, 3.55, 0], color=P["a"], width=4, seed=62),
        ]
        for index, (x, label, color) in enumerate(((-2.65, "CHIPS", P["c"]), (0, "DISTILL", P["b"]), (2.65, "TEST BOTH", P["a"]))):
            response_parts.extend(
                [
                    ink_circle([x, 3.02, 0], 0.42, color=color, width=4, seed=70 + index),
                    tiny_label(label, [x, 3.02, 0], color=color, size=19),
                ]
            )
        visual.add(semantic_part("policy_response", *response_parts))
    return visual


def gear(center, radius, color, teeth=10):
    parts = VGroup(
        Circle(radius=radius, stroke_color=color, stroke_width=3.5, stroke_opacity=0.88).move_to(center),
        Circle(radius=radius * 0.24, stroke_color=color, stroke_width=3, stroke_opacity=0.72).move_to(center),
    )
    for index in range(teeth):
        angle = TAU * index / teeth
        start = center + np.array([np.cos(angle), np.sin(angle), 0]) * radius
        end = center + np.array([np.cos(angle), np.sin(angle), 0]) * (radius + 0.18)
        parts.add(Line(start, end, color=color, stroke_width=3, stroke_opacity=0.8))
    return parts


def papyrus_visual(stage):
    visual = VGroup()
    center = np.array([0, 0.35, 0])
    ring = ink_circle(center, 1.18, color=P["b"], width=5, seed=90)
    visual.add(
        semantic_part(
            "open_weights_core",
            ring,
            gear(center, 0.78, P["c"], teeth=12),
            fit_text("OPEN", max_width=1.2, size=28, color=P["ink"], weight=BOLD).move_to(center),
        )
    )
    if stage < 4:
        visual.add(
            semantic_part(
                "framing",
                tiny_label("an engine of access", [0, 2.25, 0], color=P["a"], size=29, rotation=-0.018),
            )
        )
    if stage >= 1:
        benefit_parts = []
        nodes = ((-2.7, 1.25, "ACCESS"), (0, -2.1, "CHOICE"), (2.7, 1.25, "CONTROL"))
        for index, (x, y, label) in enumerate(nodes):
            point = np.array([x, y, 0])
            benefit_parts.extend(
                [
                    gear(point, 0.43, (P["a"], P["c"], P["b"])[index], teeth=8),
                    tiny_label(label, point + DOWN * 0.72, color=P["ink"], size=21),
                    ink_line(center, point, color=P["muted"], width=3, seed=100 + index, opacity=0.7),
                ]
            )
        visual.add(semantic_part("shared_benefits", *benefit_parts))
    if stage >= 2:
        irreversible_parts = [
            Arc(radius=2.35, start_angle=PI * 1.08, angle=PI * 0.84, color=P["a"], stroke_width=5).shift(DOWN * 1.0),
            Arrow([2.18, -1.85, 0], [2.55, -1.5, 0], buff=0, color=P["a"], stroke_width=4, max_tip_length_to_length_ratio=0.32),
        ]
        if stage == 2:
            irreversible_parts.append(
                tiny_label("the wheel only turns forward", [0, -3.45, 0], color=P["a"], size=25, rotation=0.018)
            )
        visual.add(semantic_part("irreversibility", *irreversible_parts))
    if stage >= 3:
        stand = ink_line([0, -4.1, 0], [0, -3.2, 0], color=P["ink"], width=4, seed=118)
        beam = ink_line([-2.7, -3.3, 0], [2.7, -3.7, 0], color=P["ink"], width=4, seed=119)
        visual.add(
            semantic_part(
                "attacker_defender",
                stand,
                beam,
                gear([-2.35, -3.01, 0], 0.35, P["b"], teeth=8),
                gear([2.35, -3.97, 0], 0.48, P["a"], teeth=8),
                tiny_label("defense", [-2.35, -3.7, 0], color=P["b"], size=22),
                tiny_label("misuse", [2.35, -4.65, 0], color=P["a"], size=22),
            )
        )
    if stage >= 4:
        response_parts = [
            tiny_label("frontier safety governor", [0, 3.82, 0], color=P["b"], size=28, rotation=-0.015),
            ink_line([-1.65, 3.54, 0], [1.7, 3.57, 0], color=P["b"], width=4, seed=131),
        ]
        for index, (x, label, color) in enumerate(((-2.65, "CHIPS", P["c"]), (0, "DISTILL", P["a"]), (2.65, "TEST", P["b"]))):
            knob = VGroup(
                Arc(radius=0.42, start_angle=0.15, angle=PI * 1.7, color=color, stroke_width=4),
                Line([x, 3.05, 0], [x + 0.22, 3.33, 0], color=color, stroke_width=4),
                tiny_label(label, [x, 2.5, 0], color=color, size=20),
            )
            knob[0].move_to([x, 3.13, 0])
            response_parts.append(knob)
        visual.add(semantic_part("policy_response", *response_parts))
    return visual


def future_node(point, label, color, radius=0.43):
    halo = Circle(radius=radius * 1.25, stroke_color=color, stroke_width=1, stroke_opacity=0.25).move_to(point)
    ring = Circle(radius=radius, stroke_color=color, stroke_width=3, stroke_opacity=0.92).move_to(point)
    dot = Dot(point, radius=0.07, color=color)
    text = tiny_label(label, np.array(point) + DOWN * (radius + 0.38), color=color, size=19)
    return VGroup(halo, ring, dot, text)


def future_visual(stage):
    visual = VGroup()
    core = np.array([0, 0.35, 0])
    visual.add(
        semantic_part(
            "open_weights_core",
            Circle(radius=1.12, stroke_color=P["a"], stroke_width=2, stroke_opacity=0.55).move_to(core),
            Circle(radius=0.92, stroke_color=P["a"], stroke_width=5, stroke_opacity=0.95).move_to(core),
            fit_text("WEIGHTS", max_width=1.45, size=26, color=P["ink"], weight=BOLD).move_to(core),
        )
    )
    if stage < 4:
        visual.add(
            semantic_part(
                "framing",
                tiny_label("THE FRONTIER VARIABLE", [0, 2.35, 0], color=P["a"], size=23),
            )
        )
    if stage >= 1:
        benefit_parts = []
        nodes = ((-2.8, 1.15, "ACCESS", P["a"]), (0, -2.05, "COMPETE", P["c"]), (2.8, 1.15, "CONTROL", P["b"]))
        for x, y, label, color in nodes:
            point = np.array([x, y, 0])
            benefit_parts.extend(
                [
                    Line(core, point, color=color, stroke_width=2, stroke_opacity=0.55),
                    future_node(point, label, color),
                ]
            )
        visual.add(semantic_part("shared_benefits", *benefit_parts))
    if stage >= 2:
        irreversible_parts = []
        for radius, opacity in ((1.75, 0.34), (2.25, 0.22), (2.75, 0.12)):
            irreversible_parts.append(
                Arc(radius=radius, start_angle=PI * 1.08, angle=PI * 0.84, color=P["b"], stroke_width=2, stroke_opacity=opacity).shift(DOWN * 0.5)
            )
        if stage == 2:
            irreversible_parts.append(
                tiny_label("IRREVERSIBLE RELEASE", [0, -3.45, 0], color=P["b"], size=24)
            )
        visual.add(semantic_part("irreversibility", *irreversible_parts))
    if stage >= 3:
        left_bar = Line([-3.05, -3.8, 0], [-0.35, -3.8, 0], color=P["a"], stroke_width=14)
        right_bar = Line([0.35, -3.8, 0], [3.45, -3.8, 0], color=P["b"], stroke_width=14)
        visual.add(
            semantic_part(
                "attacker_defender",
                left_bar,
                right_bar,
                tiny_label("DEFENSE", [-2.0, -4.25, 0], color=P["a"], size=20),
                tiny_label("ATTACK", [2.05, -4.25, 0], color=P["b"], size=20),
                tiny_label("NET BENEFIT?", [0, -4.75, 0], color=P["ink"], size=26),
            )
        )
    if stage >= 4:
        response_parts = [
            tiny_label("NO BAN // TEST THE THRESHOLD", [0, 3.82, 0], color=P["c"], size=23)
        ]
        for index, (x, label, color) in enumerate(((-2.65, "CHIP\nCONTROL", P["c"]), (0, "STOP\nDISTILL", P["b"]), (2.65, "TEST\nBOTH", P["a"]))):
            response_parts.append(future_node([x, 3.05, 0], label, color, radius=0.32))
        response_parts.append(
            Line([-3.0, 3.05, 0], [3.0, 3.05, 0], color=P["muted"], stroke_width=1, stroke_opacity=0.35)
        )
        visual.add(semantic_part("policy_response", *response_parts))
    return visual


def torn_sheet(center, color, tilt, heading):
    x, y = center
    points = [
        [x - 1.45, y - 2.0, 0], [x + 1.35, y - 1.86, 0], [x + 1.5, y - 0.85, 0],
        [x + 1.3, y + 2.0, 0], [x - 1.35, y + 1.88, 0], [x - 1.52, y + 0.65, 0],
    ]
    sheet = Polygon(*points, fill_color=color, fill_opacity=0.13, stroke_color=color, stroke_width=3)
    lines = VGroup(*[
        Line([x - 0.9, y + 0.75 - index * 0.42, 0], [x + 0.85, y + 0.72 - index * 0.42, 0], color=color, stroke_width=2, stroke_opacity=0.38)
        for index in range(5)
    ])
    title = fit_text(heading, max_width=2.0, size=25, color=color, weight=BOLD).move_to([x, y + 1.28, 0])
    return VGroup(sheet, lines, title).rotate(tilt, about_point=[x, y, 0])


def director_visual(stage):
    visual = VGroup()
    left = torn_sheet((-1.72, 0.35), P["a"], -0.055, "OPEN LETTER")
    right = torn_sheet((1.72, 0.35), P["b"], 0.045, "RESPONSE")
    visual.add(semantic_part("open_weights_core", left, right))
    if stage < 4:
        visual.add(
            semantic_part(
                "framing",
                fit_text("AGREE", max_width=1.7, size=35, color=P["c"], weight=BOLD).move_to([0, 2.85, 0]),
                tiny_label("more than the headline", [0, 2.38, 0], color=P["ink"], size=22),
            )
        )
    if stage >= 1:
        benefit_parts = []
        for index, (y, label, color) in enumerate(((1.25, "ACCESS", P["a"]), (0.35, "COMPETITION", P["c"]), (-0.55, "CONTROL", P["b"]))):
            benefit_parts.extend(
                [
                    Line([-2.65, y, 0], [2.65, y, 0], color=color, stroke_width=8, stroke_opacity=0.8),
                    fit_text(label, max_width=2.6, size=23, color=P["ink"], weight=BOLD).move_to([0, y, 0]),
                ]
            )
        visual.add(semantic_part("shared_benefits", *benefit_parts))
    if stage >= 2:
        burst = VGroup()
        for index in range(14):
            angle = TAU * index / 14
            start = np.array([0, -2.25, 0]) + np.array([np.cos(angle), np.sin(angle), 0]) * 0.35
            end = np.array([0, -2.25, 0]) + np.array([np.cos(angle), np.sin(angle), 0]) * (0.8 + 0.15 * (index % 3))
            burst.add(Line(start, end, color=P["a"] if index % 2 else P["b"], stroke_width=4))
        visual.add(
            semantic_part(
                "irreversibility",
                burst,
                fit_text("NO UNDO", max_width=1.7, size=27, color=P["ink"], weight=BOLD).move_to([0, -2.25, 0]),
            )
        )
    if stage >= 3:
        visual.add(
            semantic_part(
                "attacker_defender",
                Arrow([-3.0, -3.75, 0], [-0.25, -3.75, 0], color=P["b"], stroke_width=8, buff=0),
                Arrow([3.0, -3.75, 0], [0.25, -3.75, 0], color=P["a"], stroke_width=8, buff=0),
                tiny_label("DEFENDERS", [-2.1, -4.25, 0], color=P["b"], size=21),
                tiny_label("ATTACKERS", [2.1, -4.25, 0], color=P["a"], size=21),
                fit_text("WHO GAINS MORE?", max_width=3.2, size=27, color=P["c"], weight=BOLD).move_to([0, -4.85, 0]),
            )
        )
    if stage >= 4:
        response_parts = [
            fit_text("DRAW THE SAFETY LINE", max_width=4.6, size=29, color=P["ink"], weight=BOLD).move_to([0, 3.82, 0])
        ]
        for x, label, color in ((-2.65, "CHIPS", P["c"]), (0, "DISTILL", P["a"]), (2.65, "TEST BOTH", P["b"])):
            response_parts.extend(
                [
                    Circle(radius=0.43, fill_color=color, fill_opacity=0.16, stroke_color=color, stroke_width=3).move_to([x, 3.05, 0]),
                    tiny_label(label, [x, 3.05, 0], color=color, size=19),
                ]
            )
        visual.add(semantic_part("policy_response", *response_parts))
    return visual


def story_stage(index):
    if not STORY_STAGES:
        return {"label": "SOURCE-BACKED IDEA", "role": "CLAIM"}
    return STORY_STAGES[min(index, len(STORY_STAGES) - 1)]


def story_color(index):
    return (P["a"], P["b"], P["c"], P["a"])[index % 4]


def story_label(value, point, max_width=1.65, max_height=0.68, chars=12, lines=2, size=23, color=None, complete=False):
    text_builder = complete_wrap_text if complete else wrap_text
    text = text_builder(
        value,
        max_width=max_width,
        max_height=max_height,
        chars=chars,
        lines=lines,
        size=size,
        color=color or P["ink"],
        weight=BOLD,
    )
    return text.move_to(point)


def mechanism_path(points, color=None, width=4, seed=1, closed=False, opacity=1.0):
    if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
        return ink_path(
            points,
            color=color or P["ink"],
            width=width,
            seed=seed,
            closed=closed,
            opacity=opacity,
        )
    raw = [np.array(point, dtype=float) for point in points]
    if closed:
        raw.append(raw[0])
    path = VMobject()
    if len(raw) > 4:
        path.set_points_smoothly(raw)
    else:
        path.set_points_as_corners(raw)
    path.set_stroke(color or P["ink"], width=width, opacity=opacity)
    return path


def mechanism_circle(center, radius, color=None, width=4, seed=1, opacity=1.0):
    if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
        return ink_circle(center, radius, color=color or P["ink"], width=width, seed=seed, opacity=opacity)
    return Circle(
        radius=radius,
        stroke_color=color or P["ink"],
        stroke_width=width,
        stroke_opacity=opacity,
        fill_color=color or P["ink"],
        fill_opacity=0.055,
    ).move_to(center)


def mechanism_ellipse(center, width, height, color=None, stroke_width=4, seed=1, opacity=1.0):
    points = []
    for index in range(49):
        angle = TAU * index / 48
        points.append(
            [
                center[0] + width * 0.5 * np.cos(angle),
                center[1] + height * 0.5 * np.sin(angle),
                0,
            ]
        )
    return mechanism_path(
        points,
        color=color,
        width=stroke_width,
        seed=seed,
        closed=True,
        opacity=opacity,
    )


def mechanism_arrow(start, end, color=None, width=5, seed=1, opacity=1.0):
    if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
        return ink_arrow(start, end, color=color or P["ink"], width=width, seed=seed, opacity=opacity)
    return Arrow(
        start,
        end,
        buff=0.08,
        color=color or P["ink"],
        stroke_width=width,
        stroke_opacity=opacity,
        max_tip_length_to_length_ratio=0.18,
    )


def mechanism_dot(point, color=None, radius=0.1):
    color = color or P["ink"]
    if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
        return VGroup(
            Dot(point, radius=radius, color=color),
            mechanism_circle(point, radius * 1.75, color=color, width=2, seed=301, opacity=0.45),
        )
    return VGroup(
        Dot(point, radius=radius, color=color),
        Circle(radius=radius * 2.0, stroke_color=color, stroke_width=1, stroke_opacity=0.3).move_to(point),
    )


def semantic_part(key, *items):
    part = VGroup(*items)
    part.semantic_id = key
    return part


def technology_part(key, *items):
    part = Group(*items)
    part.semantic_id = key
    return part


def technology_label(value, point, color=None, size=28, max_width=3.2):
    return fit_text(
        value,
        max_width=max_width,
        size=size,
        color=color or P["ink"],
        weight=BOLD,
    ).move_to(point)


def technology_adolescence_visual(stage, phase=0):
    """A quiet editorial composition made only of one-shot semantic reveals."""
    visual = Group()
    if stage == 0:
        visual.add(
            technology_part(
                "baseline",
                Line(
                    [-3.05, -1.45, 0],
                    [3.05, -1.45, 0],
                    color=P["muted"],
                    stroke_width=2,
                    stroke_opacity=0.24,
                ),
            )
        )
        if phase >= 1:
            power_path = VMobject()
            power_path.set_points_smoothly(
                [
                    [-2.8, -1.02, 0],
                    [-1.72, -0.50, 0],
                    [-0.58, 0.38, 0],
                    [0.70, 1.55, 0],
                    [2.70, 2.72, 0],
                ]
            )
            power_path.set_stroke(P["a"], width=8, opacity=1)
            visual.add(
                technology_part(
                    "power",
                    power_path,
                    Dot([2.70, 2.72, 0], radius=0.12, color=P["a"]),
                    technology_label(
                        "POWER",
                        [1.78, 2.75, 0],
                        color=P["a"],
                        size=27,
                        max_width=1.55,
                    ),
                )
            )
        if phase >= 2:
            maturity_path = VMobject()
            maturity_path.set_points_smoothly(
                [
                    [-2.8, -1.02, 0],
                    [-1.45, -0.88, 0],
                    [0.05, -0.67, 0],
                    [1.35, -0.40, 0],
                    [2.70, -0.10, 0],
                ]
            )
            maturity_path.set_stroke(P["c"], width=7, opacity=1)
            gap = DoubleArrow(
                [2.70, 0.10, 0],
                [2.70, 2.48, 0],
                color=P["b"],
                stroke_width=3,
                buff=0.05,
                max_tip_length_to_length_ratio=0.08,
            )
            visual.add(
                technology_part(
                    "maturity",
                    maturity_path,
                    Dot([2.70, -0.10, 0], radius=0.11, color=P["c"]),
                    technology_label(
                        "MATURITY",
                        [1.65, -0.73, 0],
                        color=P["c"],
                        size=25,
                        max_width=2.15,
                    ),
                    gap,
                )
            )
        return visual

    if stage == 1:
        image = ImageMobject(TECHNOLOGY_IMAGE_PATH)
        image.set_height(4.10).move_to([0, 0.38, 0]).set_opacity(0.86)
        shade = Rectangle(
            width=6.26,
            height=4.12,
            fill_color=SPEC["background"],
            fill_opacity=0.20,
            stroke_opacity=0,
        ).move_to(image)
        frame = RoundedRectangle(
            corner_radius=0.14,
            width=6.36,
            height=4.22,
            stroke_color=P["muted"],
            stroke_width=2,
            stroke_opacity=0.48,
            fill_opacity=0,
        ).move_to(image)
        visual.add(technology_part("server_photo", image, shade, frame))
        if phase >= 1:
            nodes = Group(
                *[
                    Dot(
                        [
                            -2.42 + (index % 7) * 0.80,
                            1.58 - (index // 7) * 1.02,
                            0,
                        ],
                        radius=0.055,
                        color=P["c"] if index % 3 else P["a"],
                    )
                    for index in range(21)
                ]
            )
            visual.add(technology_part("parallel_minds", nodes))
        if phase >= 2:
            scale_text = (
                "MILLIONS OF COPIES"
                if phase == 2
                else "MILLIONS, FASTER THAN US"
            )
            visual.add(
                technology_part(
                    "scale_label",
                    technology_label(
                        scale_text,
                        [0, -2.33, 0],
                        color=P["ink"],
                        size=28,
                        max_width=5.7,
                    ),
                    Line(
                        [-2.75, -2.02, 0],
                        [2.75, -2.02, 0],
                        color=P["a"],
                        stroke_width=3,
                        stroke_opacity=0.78,
                    ),
                )
            )
        return visual

    if stage == 2:
        center = np.array([0.0, 0.15, 0.0])
        visual.add(
            technology_part(
                "four_tests",
                Circle(
                    radius=0.58,
                    color=P["ink"],
                    stroke_width=3,
                    fill_color=SPEC["background"],
                    fill_opacity=1,
                ).move_to(center),
                technology_label(
                    "4 TESTS",
                    center,
                    color=P["ink"],
                    size=22,
                    max_width=1.05,
                ),
            )
        )
        risks = (
            ("autonomy", "AUTONOMY", [-2.45, 2.10, 0], P["a"]),
            ("destruction", "DESTRUCTION", [2.45, 2.10, 0], P["b"]),
            ("political_power", "POLITICAL POWER", [-2.45, -1.85, 0], P["c"]),
            ("economic_shock", "ECONOMIC SHOCK", [2.45, -1.85, 0], P["a"]),
        )
        for index, (key, label, point, color) in enumerate(risks, start=1):
            if phase < index:
                continue
            point_array = np.array(point, dtype=float)
            visual.add(
                technology_part(
                    key,
                    Line(
                        center,
                        point_array,
                        color=color,
                        stroke_width=3,
                        stroke_opacity=0.72,
                    ),
                    Circle(
                        radius=0.28,
                        color=color,
                        stroke_width=5,
                    ).move_to(point_array),
                    Dot(point_array, radius=0.075, color=color),
                    technology_label(
                        label,
                        point_array + DOWN * 0.62,
                        color=color,
                        size=22,
                        max_width=2.65,
                    ),
                )
            )
        return visual

    if stage == 3:
        points = (
            (-2.95, "UNCERTAINTY", P["b"]),
            (-0.98, "EVIDENCE", P["a"]),
            (0.98, "DEFENSES", P["c"]),
            (2.95, "TARGETED ACTION", P["a"]),
        )
        visual.add(
            technology_part(
                "response_path",
                Line(
                    [-3.05, 0.30, 0],
                    [3.05, 0.30, 0],
                    color=P["muted"],
                    stroke_width=4,
                    stroke_opacity=0.28,
                ),
            )
        )
        for index, (x, label, color) in enumerate(points, start=1):
            if phase < index:
                continue
            visual.add(
                technology_part(
                    f"response_{index}",
                    Dot([x, 0.30, 0], radius=0.15, color=color),
                    Circle(
                        radius=0.32,
                        color=color,
                        stroke_width=2,
                        stroke_opacity=0.65,
                    ).move_to([x, 0.30, 0]),
                    technology_label(
                        label,
                        [x, -0.48 if index % 2 else 1.06, 0],
                        color=color,
                        size=19,
                        max_width=1.85,
                    ),
                )
            )
        return visual

    left = np.array([-2.85, -0.95, 0.0])
    right = np.array([2.85, -0.95, 0.0])
    visual.add(
        technology_part(
            "final_anchors",
            Dot(left, radius=0.13, color=P["a"]),
            Dot(right, radius=0.13, color=P["c"]),
            technology_label(
                "POWER",
                left + DOWN * 0.52,
                color=P["a"],
                size=24,
                max_width=1.4,
            ),
            technology_label(
                "MATURITY",
                right + DOWN * 0.52,
                color=P["c"],
                size=24,
                max_width=1.8,
            ),
        )
    )
    if phase >= 1:
        bridge = ArcBetweenPoints(
            left,
            right,
            angle=-PI / 2.6,
            color=P["ink"],
            stroke_width=6,
        )
        marker_alpha = 0.12 if phase == 1 else 0.88
        marker = Dot(
            bridge.point_from_proportion(marker_alpha),
            radius=0.16,
            color=P["b"],
        )
        visual.add(technology_part("bridge", bridge))
        visual.add(technology_part("human_marker", marker))
    if phase >= 2:
        visual.add(
            technology_part(
                "final_question",
                technology_label(
                    "CAN WE GROW UP FAST ENOUGH?",
                    [0, 2.25, 0],
                    color=P["ink"],
                    size=34,
                    max_width=6.7,
                ),
            )
        )
    return visual


def mechanism_orbit_visual(stage):
    visual = VGroup()
    earth_center = np.array([0.0, -0.45, 0.0])
    earth = mechanism_circle(earth_center, 1.03, color=P["a"], width=6, seed=310)
    visual.add(
        semantic_part(
            "earth",
            earth,
            mechanism_path(
                [[-0.65, -0.25, 0], [-0.2, 0.12, 0], [0.35, 0.0, 0], [0.66, -0.4, 0]],
                color=P["a"],
                width=3,
                seed=311,
                opacity=0.55,
            ),
            tiny_label("EARTH", [0, -0.48, 0], color=P["a"], size=21),
        )
    )
    satellite_point = np.array([-2.55, 1.35, 0.0])
    visual.add(semantic_part("satellite", mechanism_dot(satellite_point, color=P["c"], radius=0.11)))
    visual.add(
        semantic_part(
            "gravity",
            mechanism_arrow(
                satellite_point + DOWN * 0.08,
                earth_center + UP * 0.85,
                color=P["b"],
                width=5,
                seed=314,
            ),
            tiny_label("GRAVITY", [-1.75, 0.25, 0], color=P["b"], size=19, rotation=-0.28),
        )
    )
    if stage >= 1:
        visual.add(
            semantic_part(
                "velocity",
                mechanism_arrow(
                    satellite_point,
                    satellite_point + RIGHT * 1.65 + UP * 0.08,
                    color=P["c"],
                    width=5,
                    seed=318,
                ),
                tiny_label("SIDEWAYS VELOCITY", [-1.65, 1.87, 0], color=P["c"], size=18, rotation=0.02),
                mechanism_path(
                    [[-2.8, 1.3, 0], [-2.2, 1.58, 0], [-1.55, 1.63, 0], [-0.95, 1.38, 0]],
                    color=P["c"],
                    width=4,
                    seed=319,
                    opacity=0.72,
                ),
            )
        )
    if stage >= 2:
        visual.add(
            semantic_part(
                "closed_orbit",
                mechanism_ellipse(
                    earth_center,
                    6.1,
                    3.75,
                    color=P["a"],
                    stroke_width=5,
                    seed=322,
                    opacity=0.78,
                ),
                tiny_label("THE FALL KEEPS CURVING", [0, -2.75, 0], color=P["a"], size=21),
            )
        )
    if stage >= 3:
        visual.add(
            semantic_part(
                "speed_paths",
                mechanism_path(
                    [[-2.9, 0.82, 0], [-1.65, 0.38, 0], [-0.95, -0.45, 0]],
                    color=P["b"],
                    width=4,
                    seed=326,
                    opacity=0.72,
                ),
                mechanism_path(
                    [[-2.9, 1.85, 0], [-1.4, 2.42, 0], [0.55, 2.25, 0], [2.55, 1.22, 0]],
                    color=P["c"],
                    width=4,
                    seed=327,
                    opacity=0.72,
                ),
                tiny_label("TOO SLOW", [-2.25, -0.05, 0], color=P["b"], size=17, rotation=-0.25),
                tiny_label("MORE SPEED", [1.75, 2.18, 0], color=P["c"], size=17, rotation=-0.08),
            )
        )
    if stage >= 4:
        visual.add(
            semantic_part(
                "payoff",
                mechanism_ellipse(
                    earth_center,
                    6.35,
                    3.95,
                    color=P["c"],
                    stroke_width=3,
                    seed=331,
                    opacity=0.36,
                ),
                tiny_label("FALLING AROUND EARTH", [0, 3.0, 0], color=P["c"], size=25),
                tiny_label("NO CONSTANT THRUST", [0, -3.35, 0], color=P["ink"], size=22),
            )
        )
    return visual


def loss_point(x):
    return np.array([x, 0.38 * x * x - 1.25, 0.0])


def mechanism_gradient_visual(stage):
    visual = VGroup()
    visual.add(
        semantic_part(
            "axes",
            mechanism_path(
                [[-3.35, -1.5, 0], [3.35, -1.5, 0]],
                color=P["muted"],
                width=3,
                seed=340,
                opacity=0.5,
            ),
            mechanism_path(
                [[-3.15, -1.75, 0], [-3.15, 2.35, 0]],
                color=P["muted"],
                width=3,
                seed=341,
                opacity=0.5,
            ),
            tiny_label("LOSS", [-3.35, 2.6, 0], color=P["a"], size=20),
            tiny_label("PARAMETERS", [2.45, -1.88, 0], color=P["muted"], size=17),
        )
    )
    curve_points = [loss_point(-2.9 + index * 0.145) for index in range(41)]
    visual.add(
        semantic_part(
            "loss_curve",
            mechanism_path(curve_points, color=P["a"], width=6, seed=342),
        )
    )
    points = [loss_point(x) for x in (-2.5, -1.58, -0.88, -0.28)]
    visual.add(
        semantic_part(
            "starting_point",
            mechanism_dot(points[0], color=P["b"], radius=0.12),
        )
    )
    if stage == 0:
        visual.add(
            semantic_part(
                "intro_label",
                tiny_label("CURRENT MODEL", points[0] + UP * 0.52, color=P["b"], size=18),
            )
        )
    if stage >= 1:
        visual.add(
            semantic_part(
                "gradient_direction",
                mechanism_arrow(points[1], points[0], color=P["b"], width=5, seed=346),
                mechanism_arrow(points[1], points[2], color=P["c"], width=5, seed=347),
                tiny_label("GRADIENT = UPHILL", [-1.85, 2.18, 0], color=P["b"], size=18, rotation=-0.13),
                tiny_label("DESCENT = OPPOSITE", [-0.55, -0.1, 0], color=P["c"], size=18, rotation=-0.1),
            )
        )
    if stage >= 2:
        step_items = []
        for index, point in enumerate(points[1:], start=1):
            step_items.append(mechanism_dot(point, color=story_color(index), radius=0.1))
        for index in range(len(points) - 1):
            step_items.append(
                mechanism_arrow(
                    points[index],
                    points[index + 1],
                    color=P["c"],
                    width=3,
                    seed=350 + index,
                    opacity=0.78,
                )
            )
        step_items.append(tiny_label("RECALCULATE", [0.35, 1.25, 0], color=P["c"], size=19))
        visual.add(semantic_part("iterative_steps", *step_items))
    if stage >= 3:
        visual.add(
            semantic_part(
                "learning_rate",
                mechanism_arrow([-2.55, -2.45, 0], [-1.9, -2.45, 0], color=P["a"], width=4, seed=356),
                mechanism_arrow([-1.25, -2.45, 0], [0.55, -2.45, 0], color=P["b"], width=4, seed=357),
                tiny_label("SMALL STEP", [-2.25, -2.85, 0], color=P["a"], size=16),
                tiny_label("OVERSHOOT", [-0.35, -2.85, 0], color=P["b"], size=16),
                tiny_label("LEARNING RATE", [2.35, -2.55, 0], color=P["ink"], size=18),
            )
        )
    if stage >= 4:
        minimum = loss_point(0.0)
        visual.add(
            semantic_part(
                "payoff",
                mechanism_circle(minimum, 0.32, color=P["c"], width=5, seed=361),
                tiny_label("LOWER LOSS", [1.15, 0.15, 0], color=P["c"], size=24),
                tiny_label("REPEAT THE UPDATE", [0, 3.0, 0], color=P["ink"], size=23),
            )
        )
    return visual


def mechanism_attention_visual(stage):
    visual = VGroup()
    tokens = ("THE", "MODEL", "LEARNS", "CONTEXT")
    x_positions = (-2.75, -0.92, 0.92, 2.75)
    colors = (P["muted"], P["c"], P["a"], P["b"])
    token_items = []
    for index, (token, x, color) in enumerate(zip(tokens, x_positions, colors)):
        token_items.extend(
            [
                fit_text(token, max_width=1.45, size=24, color=color, weight=BOLD).move_to([x, 2.55, 0]),
                mechanism_path(
                    [[x - 0.62, 2.18, 0], [x + 0.62, 2.18, 0]],
                    color=color,
                    width=3,
                    seed=370 + index,
                ),
                tiny_label("Q   K   V", [x, 1.78, 0], color=color, size=15),
            ]
        )
    visual.add(semantic_part("tokens", *token_items))
    target = np.array([-0.92, 1.45, 0.0])
    visual.add(
        semantic_part(
            "target_query",
            mechanism_circle(target, 0.22, color=P["c"], width=4, seed=376),
            tiny_label("TARGET QUERY", [-1.65, 0.93, 0], color=P["c"], size=17),
        )
    )
    key_points = [np.array([x, 1.35, 0]) for x in x_positions]
    if stage >= 1:
        score_items = []
        for index, point in enumerate(key_points):
            score_items.append(mechanism_dot(point, color=colors[index], radius=0.075))
            score_items.append(
                mechanism_path(
                    [target, [(target[0] + point[0]) / 2, 0.55 - 0.12 * index, 0], point],
                    color=colors[index],
                    width=2 + index % 3,
                    seed=380 + index,
                    opacity=0.42 + index * 0.12,
                )
            )
        score_items.append(
            fit_text("QUERY SCORES THE KEYS", max_width=4.6, size=21, color=P["ink"], weight=BOLD).move_to([0, 0.18, 0])
        )
        visual.add(semantic_part("key_scores", *score_items))
    if stage >= 2:
        weights_y = -0.65
        widths = (2, 6, 4, 3)
        weight_items = []
        for index, (x, color, line_width) in enumerate(zip(x_positions, colors, widths)):
            weight_items.append(
                mechanism_path(
                    [[x, 0.95, 0], [x, weights_y, 0]],
                    color=color,
                    width=line_width,
                    seed=388 + index,
                    opacity=0.82,
                )
            )
            weight_items.append(
                mechanism_dot(
                    [x, weights_y, 0],
                    color=color,
                    radius=0.07 + 0.02 * (line_width > 3),
                )
            )
        weight_items.append(
            fit_text("SOFTMAX → NORMALIZED WEIGHTS", max_width=4.9, size=20, color=P["c"], weight=BOLD).move_to([0, -1.12, 0])
        )
        visual.add(semantic_part("softmax_weights", *weight_items))
    output = np.array([0.0, -2.75, 0.0])
    if stage >= 3:
        context_items = []
        for index, (x, color) in enumerate(zip(x_positions, colors)):
            context_items.append(
                mechanism_arrow(
                    [x, -0.82, 0],
                    output + np.array([(index - 1.5) * 0.08, 0.28, 0]),
                    color=color,
                    width=3,
                    seed=395 + index,
                    opacity=0.72,
                )
            )
        context_items.extend(
            [
                mechanism_circle(output, 0.62, color=P["a"], width=5, seed=401),
                story_label(
                    "CONTEXT",
                    output,
                    max_width=1.1,
                    max_height=0.4,
                    chars=8,
                    size=19,
                    color=P["a"],
                ),
            ]
        )
        context_items.append(
            fit_text("WEIGHTED VALUES COMBINE", max_width=4.6, size=19, color=P["a"], weight=BOLD).move_to([0, -3.65, 0])
        )
        visual.add(semantic_part("context_output", *context_items))
    if stage >= 4:
        visual.add(
            semantic_part(
                "multiple_heads",
                mechanism_path(
                    [[-3.0, 3.25, 0], [-1.2, 3.55, 0], [0.4, 3.2, 0], [2.95, 3.52, 0]],
                    color=P["b"],
                    width=4,
                    seed=405,
                ),
                mechanism_path(
                    [[-3.0, 3.55, 0], [-0.8, 3.18, 0], [1.15, 3.55, 0], [2.95, 3.28, 0]],
                    color=P["c"],
                    width=4,
                    seed=406,
                ),
                fit_text(
                    "MULTIPLE HEADS • DIFFERENT RELATIONSHIPS",
                    max_width=6.0,
                    size=21,
                    color=P["ink"],
                    weight=BOLD,
                ).move_to([0, 4.0, 0]),
            )
        )
    return visual


def bayes_coin(center, label, color):
    return VGroup(
        mechanism_circle(center, 0.34, color=color, width=4, seed=420 + int((center[0] + 4) * 10)),
        fit_text(label, max_width=0.42, size=22, color=color, weight=BOLD).move_to(center),
    )


def bayes_bar(x, value, value_text, color, seed):
    bottom = -1.95
    max_height = 3.0
    height = max(0.16, max_height * value)
    center_y = bottom + height * 0.5
    fill = Rectangle(
        width=1.28,
        height=height,
        stroke_width=0,
        fill_color=color,
        fill_opacity=0.17 if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"} else 0.28,
    ).move_to([x, center_y, 0])
    outline = mechanism_path(
        [
            [x - 0.64, bottom, 0],
            [x - 0.64, bottom + height, 0],
            [x + 0.64, bottom + height, 0],
            [x + 0.64, bottom, 0],
        ],
        color=color,
        width=5,
        seed=seed,
        opacity=0.94,
    )
    value_label = fit_text(
        value_text,
        max_width=1.55,
        size=26,
        color=color,
        weight=BOLD,
    ).move_to([x, bottom + height + 0.35, 0])
    return VGroup(fill, outline, value_label)


def mechanism_bayes_visual(stage, phase=0):
    visual = VGroup()
    fair_x = -1.85
    trick_x = 1.85
    if stage <= 1 or (stage == 2 and phase == 0):
        fair_value, trick_value = 0.5, 0.5
        fair_text, trick_text = "50%", "50%"
    elif stage == 2 or (stage == 3 and phase == 0):
        fair_value, trick_value = 0.125, 0.5
        fair_text, trick_text = "1/8", "1/2"
    else:
        fair_value, trick_value = 0.2, 0.8
        fair_text, trick_text = "20%", "80%"

    visual.add(
        semantic_part(
            "hypotheses",
            fit_text("FAIR COIN", max_width=2.0, size=23, color=P["a"], weight=BOLD).move_to([fair_x, 1.78, 0]),
            fit_text("TRICK COIN", max_width=2.0, size=23, color=P["c"], weight=BOLD).move_to([trick_x, 1.78, 0]),
            bayes_coin(np.array([fair_x, 2.42, 0]), "H/T", P["a"]),
            bayes_coin(np.array([trick_x, 2.42, 0]), "H", P["c"]),
        )
    )
    visual.add(
        semantic_part(
            "baseline",
            mechanism_path(
                [[-3.2, -1.95, 0], [3.2, -1.95, 0]],
                color=P["muted"],
                width=3,
                seed=430,
                opacity=0.55,
            ),
        )
    )
    visual.add(
        semantic_part(
            "probability_bars",
            bayes_bar(fair_x, fair_value, fair_text, P["a"], 432),
            bayes_bar(trick_x, trick_value, trick_text, P["c"], 436),
        )
    )

    if stage == 0:
        visual.add(
            semantic_part(
                "prior",
                fit_text("PRIOR: START EQUALLY LIKELY", max_width=5.8, size=25, color=P["ink"], weight=BOLD).move_to([0, 3.35, 0]),
                tiny_label("BEFORE THE EVIDENCE", [0, -2.72, 0], color=P["muted"], size=19),
            )
        )
    if stage in {1, 2}:
        visual.add(
            semantic_part(
                "evidence",
                bayes_coin(np.array([-0.48, 3.35, 0]), "H", P["b"]),
                bayes_coin(np.array([0.48, 3.35, 0]), "H", P["b"]),
                fit_text("EVIDENCE: TWO HEADS", max_width=3.8, size=23, color=P["b"], weight=BOLD).move_to([0, 4.0, 0]),
            )
        )
        visual.add(
            semantic_part(
                "likelihoods",
                fit_text("P(HH | FAIR) = 1/4", max_width=2.7, size=20, color=P["a"], weight=BOLD).move_to([fair_x, 0.45, 0]),
                fit_text("P(HH | TRICK) = 1", max_width=2.7, size=20, color=P["c"], weight=BOLD).move_to([trick_x, 0.45, 0]),
            )
        )
    if stage == 2 and phase >= 1:
        visual.add(
            semantic_part(
                "multiplication",
                fit_text("1/2 × 1/4 = 1/8", max_width=2.6, size=21, color=P["a"], weight=BOLD).move_to([fair_x, -2.72, 0]),
                fit_text("1/2 × 1 = 1/2", max_width=2.6, size=21, color=P["c"], weight=BOLD).move_to([trick_x, -2.72, 0]),
                tiny_label("PRIOR × LIKELIHOOD", [0, -3.35, 0], color=P["ink"], size=21),
            )
        )
    if stage == 3:
        visual.add(
            semantic_part(
                "normalization",
                fit_text("NORMALIZE SO THE TOTAL = 1", max_width=5.8, size=25, color=P["ink"], weight=BOLD).move_to([0, 3.35, 0]),
                mechanism_arrow([-0.75, 2.95, 0], [fair_x, 1.25, 0], color=P["a"], width=4, seed=442, opacity=0.7),
                mechanism_arrow([0.75, 2.95, 0], [trick_x, 1.25, 0], color=P["c"], width=4, seed=443, opacity=0.7),
                tiny_label("DIVIDE BOTH WEIGHTS BY 5/8", [0, -2.72, 0], color=P["b"], size=20),
            )
        )
    if stage >= 4:
        visual.add(
            semantic_part(
                "payoff",
                fit_text("POSTERIOR AFTER TWO HEADS", max_width=5.7, size=28, color=P["ink"], weight=BOLD).move_to([0, 3.35, 0]),
                tiny_label("EVIDENCE REWEIGHTS BELIEF", [0, -2.72, 0], color=P["b"], size=22),
                mechanism_arrow([fair_x, -3.2, 0], [trick_x, -3.2, 0], color=P["c"], width=4, seed=447, opacity=0.78),
            )
        )
    return visual


def handshake_client_icon(center, color):
    x, y = center[0], center[1]
    screen = mechanism_path(
        [
            [x - 0.66, y - 0.38, 0],
            [x + 0.66, y - 0.38, 0],
            [x + 0.66, y + 0.46, 0],
            [x - 0.66, y + 0.46, 0],
        ],
        color=color,
        width=4,
        seed=720,
        closed=True,
        opacity=0.92,
    )
    base = mechanism_path(
        [[x - 0.84, y - 0.58, 0], [x - 0.48, y - 0.68, 0], [x + 0.48, y - 0.68, 0], [x + 0.84, y - 0.58, 0]],
        color=color,
        width=4,
        seed=721,
        opacity=0.88,
    )
    cursor = mechanism_dot([x, y + 0.04, 0], color=color, radius=0.07)
    return VGroup(screen, base, cursor)


def handshake_server_icon(center, color):
    x, y = center[0], center[1]
    parts = VGroup()
    for index in range(3):
        row_y = y + 0.48 - index * 0.47
        parts.add(
            mechanism_path(
                [
                    [x - 0.68, row_y - 0.18, 0],
                    [x + 0.68, row_y - 0.18, 0],
                    [x + 0.68, row_y + 0.18, 0],
                    [x - 0.68, row_y + 0.18, 0],
                ],
                color=color,
                width=4,
                seed=730 + index,
                closed=True,
                opacity=0.9,
            )
        )
        parts.add(mechanism_dot([x + 0.44, row_y, 0], color=color, radius=0.045))
    return parts


def handshake_packet(center, label, color, seed):
    return VGroup(
        mechanism_ellipse(center, 1.82, 0.62, color=color, stroke_width=4, seed=seed, opacity=0.94),
        fit_text(label, max_width=1.5, size=18, color=color, weight=BOLD).move_to(center),
    )


def handshake_key(center, color, seed):
    x, y = center[0], center[1]
    ring = mechanism_circle(center, 0.22, color=color, width=4, seed=seed, opacity=0.94)
    shaft = mechanism_path(
        [[x + 0.2, y, 0], [x + 0.68, y, 0], [x + 0.68, y - 0.17, 0], [x + 0.52, y - 0.17, 0]],
        color=color,
        width=4,
        seed=seed + 1,
        opacity=0.94,
    )
    return VGroup(ring, shaft)


def handshake_check(center, color, seed):
    x, y = center[0], center[1]
    return VGroup(
        mechanism_circle(center, 0.35, color=color, width=4, seed=seed, opacity=0.92),
        mechanism_path(
            [[x - 0.16, y, 0], [x - 0.02, y - 0.14, 0], [x + 0.2, y + 0.16, 0]],
            color=color,
            width=5,
            seed=seed + 1,
            opacity=0.96,
        ),
    )


def handshake_lock(center, color, seed):
    x, y = center[0], center[1]
    shackle_points = []
    for index in range(13):
        angle = PI - PI * index / 12
        shackle_points.append([x + 0.34 * np.cos(angle), y + 0.18 + 0.42 * np.sin(angle), 0])
    body = mechanism_path(
        [
            [x - 0.43, y - 0.42, 0],
            [x + 0.43, y - 0.42, 0],
            [x + 0.43, y + 0.16, 0],
            [x - 0.43, y + 0.16, 0],
        ],
        color=color,
        width=4,
        seed=seed + 1,
        closed=True,
        opacity=0.94,
    )
    return VGroup(
        mechanism_path(shackle_points, color=color, width=4, seed=seed, opacity=0.94),
        body,
        mechanism_dot([x, y - 0.14, 0], color=color, radius=0.055),
    )


def mechanism_handshake_visual(stage):
    visual = VGroup()
    client = np.array([-2.8, 2.55, 0.0])
    server = np.array([2.8, 2.55, 0.0])
    stage_names = ("OFFER", "DERIVE", "AUTHENTICATE", "VERIFY", "PROTECT")
    visual.add(
        semantic_part(
            "stage_status",
            tiny_label(
                f"{stage + 1} / {stage_names[min(stage, 4)]}",
                [0, 3.92, 0],
                color=story_color(stage),
                size=18,
            ),
        )
    )
    visual.add(
        semantic_part(
            "client_actor",
            handshake_client_icon(client, P["a"]),
            tiny_label("CLIENT", [client[0], 1.62, 0], color=P["a"], size=18),
        )
    )
    visual.add(
        semantic_part(
            "server_actor",
            handshake_server_icon(server, P["b"]),
            tiny_label("SERVER", [server[0], 1.62, 0], color=P["b"], size=18),
        )
    )
    visual.add(
        semantic_part(
            "channel_backbone",
            mechanism_path(
                [[-2.0, 1.42, 0], [-1.0, 1.48, 0], [0, 1.4, 0], [1.0, 1.47, 0], [2.0, 1.42, 0]],
                color=P["muted"],
                width=2,
                seed=745,
                opacity=0.34,
            ),
            tiny_label("NETWORK", [0, 1.74, 0], color=P["muted"], size=14),
        )
    )

    if stage <= 2:
        hello_parts = [
            mechanism_arrow([-1.95, 1.25, 0], [1.78, 1.25, 0], color=P["a"], width=4, seed=750, opacity=0.76),
            handshake_packet([-0.25, 1.25, 0], "CLIENT HELLO", P["a"], 751),
        ]
        if stage >= 1:
            hello_parts.extend(
                [
                    mechanism_arrow([1.95, 0.47, 0], [-1.78, 0.47, 0], color=P["b"], width=4, seed=752, opacity=0.76),
                    handshake_packet([0.25, 0.47, 0], "SERVER HELLO", P["b"], 753),
                ]
            )
        visual.add(semantic_part("hello_messages", *hello_parts))

    if stage == 0:
        visual.add(
            semantic_part(
                "key_exchange",
                handshake_key([-0.15, 0.15, 0], P["c"], 760),
                tiny_label("KEY SHARE OFFER", [0.1, -0.36, 0], color=P["c"], size=17),
            )
        )
    if stage >= 1:
        shared_secret_parts = [
            handshake_key([-2.72, 0.3, 0], P["c"], 762),
            handshake_key([2.25, 0.3, 0], P["c"], 764),
            tiny_label("DERIVED HERE", [-2.43, -0.2, 0], color=P["c"], size=14),
            tiny_label("DERIVED HERE", [2.53, -0.2, 0], color=P["c"], size=14),
            mechanism_path(
                [[-0.72, -0.06, 0], [-0.35, 0.0, 0], [0, -0.08, 0], [0.35, 0.0, 0], [0.72, -0.06, 0]],
                color=P["c"],
                width=3,
                seed=766,
                opacity=0.66,
            ),
            tiny_label("SAME SECRET", [0, -0.42, 0], color=P["c"], size=18),
        ]
        if stage == 1:
            shared_secret_parts.append(
                tiny_label("THE SECRET NEVER CROSSES", [0, -0.92, 0], color=P["ink"], size=16)
            )
        visual.add(semantic_part("shared_secrets", *shared_secret_parts))

    if stage >= 2:
        certificate = mechanism_path(
            [
                [1.6, -1.82, 0],
                [2.8, -1.82, 0],
                [2.8, -0.86, 0],
                [1.6, -0.86, 0],
            ],
            color=P["b"],
            width=4,
            seed=770,
            closed=True,
            opacity=0.88,
        )
        certificate_lines = VGroup(
            mechanism_path(
                [[1.78, -1.12, 0], [2.55, -1.12, 0]],
                color=P["b"],
                width=2,
                seed=771,
                opacity=0.64,
            ),
            mechanism_path(
                [[1.78, -1.38, 0], [2.38, -1.38, 0]],
                color=P["b"],
                width=2,
                seed=772,
                opacity=0.64,
            ),
        )
        if stage <= 3:
            visual.add(
                semantic_part(
                    "certificate_auth",
                    certificate,
                    certificate_lines,
                    handshake_check([2.78, -0.85, 0], P["a"], 773),
                    tiny_label("CERTIFICATE + SIGNATURE", [2.12, -0.58, 0], color=P["b"], size=15),
                    tiny_label("SERVER AUTHENTICATED", [0, -1.42, 0], color=P["a"], size=18),
                    mechanism_arrow([0.95, -1.35, 0], [1.48, -1.35, 0], color=P["a"], width=3, seed=774, opacity=0.7),
                )
            )
        visual.add(
            semantic_part(
                "encrypted_tunnel",
                mechanism_path(
                    [[-2.0, 1.18, 0], [-1.0, 1.08, 0], [0, 1.16, 0], [1.0, 1.07, 0], [2.0, 1.18, 0]],
                    color=P["c"],
                    width=5,
                    seed=776,
                    opacity=0.54 if stage == 2 else 0.86,
                ),
                mechanism_path(
                    [[-2.0, 1.68, 0], [-1.0, 1.78, 0], [0, 1.7, 0], [1.0, 1.79, 0], [2.0, 1.68, 0]],
                    color=P["c"],
                    width=5,
                    seed=777,
                    opacity=0.54 if stage == 2 else 0.86,
                ),
            )
        )

    if stage == 3:
        transcript_parts = [
            tiny_label("TRANSCRIPT", [0, -2.02, 0], color=P["muted"], size=15),
            mechanism_path(
                [[-1.45, -2.3, 0], [-0.72, -2.24, 0], [0, -2.31, 0], [0.72, -2.24, 0], [1.45, -2.3, 0]],
                color=P["muted"],
                width=3,
                seed=780,
                opacity=0.58,
            ),
        ]
        for index, x in enumerate((-1.2, -0.6, 0, 0.6, 1.2)):
            transcript_parts.append(
                mechanism_dot([x, -2.28, 0], color=(P["a"], P["b"], P["c"])[index % 3], radius=0.055)
            )
        visual.add(semantic_part("transcript", *transcript_parts))
    if stage >= 3:
        visual.add(
            semantic_part(
                "finished_checks",
                handshake_check([-2.45, -2.72, 0], P["a"], 784),
                handshake_check([2.45, -2.72, 0], P["b"], 786),
                mechanism_arrow([-1.9, -2.63, 0], [1.85, -2.63, 0], color=P["a"], width=3, seed=788, opacity=0.68),
                mechanism_arrow([1.9, -3.0, 0], [-1.85, -3.0, 0], color=P["b"], width=3, seed=789, opacity=0.68),
                tiny_label("FINISHED", [0, -2.48, 0], color=P["ink"], size=17),
                tiny_label("VERIFY OR ABORT", [0, -3.36, 0], color=P["b"], size=16),
            )
        )

    if stage >= 4:
        data_parts = [
            handshake_lock([0, 0.93, 0], P["c"], 792),
            mechanism_arrow([-1.78, 1.42, 0], [1.78, 1.42, 0], color=P["c"], width=5, seed=794, opacity=0.9),
            tiny_label("PROTECTED APPLICATION DATA", [0, 0.15, 0], color=P["c"], size=18),
        ]
        for index, x in enumerate((-1.25, -0.62, 0.62, 1.25)):
            data_parts.append(
                mechanism_dot([x, 1.42, 0], color=P["c"] if index % 2 else P["ink"], radius=0.07)
            )
        visual.add(semantic_part("application_data", *data_parts))
        visual.add(
            semantic_part(
                "payoff",
                mechanism_path(
                    [[-2.8, -4.0, 0], [-1.4, -3.92, 0], [0, -4.04, 0], [1.4, -3.92, 0], [2.8, -4.0, 0]],
                    color=P["c"],
                    width=4,
                    seed=798,
                    opacity=0.82,
                ),
                tiny_label("SAME KEYS • AUTHENTICATED PEER • PRIVATE TRAFFIC", [0, -4.35, 0], color=P["c"], size=15),
            )
        )
    return visual


def process_positions():
    return (
        np.array([-2.36, 2.44, 0.0]),
        np.array([2.26, 1.18, 0.0]),
        np.array([-2.12, -0.08, 0.0]),
        np.array([2.20, -1.42, 0.0]),
        np.array([-1.08, -2.84, 0.0]),
    )


def process_label_positions():
    return (
        np.array([0.42, 2.48, 0.0]),
        np.array([-0.46, 1.16, 0.0]),
        np.array([0.46, -0.04, 0.0]),
        np.array([-0.46, -1.40, 0.0]),
        np.array([1.28, -2.82, 0.0]),
    )


def process_curve_points(index, endpoint_buffer=0.0):
    positions = process_positions()
    index = min(max(1, int(index)), len(positions) - 1)
    start = positions[index - 1]
    end = positions[index]
    direction = normalize(end - start)
    sideways = np.array([-direction[1], direction[0], 0.0])
    start = start + direction * endpoint_buffer
    end = end - direction * endpoint_buffer
    bend = 0.24 if index % 2 else -0.24
    points = []
    for alpha in (0.0, 0.16, 0.34, 0.54, 0.74, 0.90, 1.0):
        wave = bend * np.sin(PI * alpha) + 0.055 * np.sin(TAU * alpha)
        points.append(interpolate(start, end, alpha) + sideways * wave)
    return points


def process_backbone_points():
    points = []
    for index in range(1, len(process_positions())):
        segment = process_curve_points(index)
        points.extend(segment if not points else segment[1:])
    return points


def process_feedback_points(endpoint_buffer=0.0):
    positions = process_positions()
    contract = (
        STORY.get("cycle_contract", {})
        if STORY.get("topology_mode") == "cycle_loop"
        else STORY.get("feedback_contract", {})
    )
    target_index = int(contract.get("return_to_stage_index", 0) or 0)
    target_index = min(max(0, target_index), len(positions) - 1)
    start = positions[-1]
    end = positions[target_index]
    start_direction = normalize(np.array([-3.18, -2.46, 0.0]) - start)
    end_direction = normalize(end - np.array([-3.18, 2.00, 0.0]))
    start = start + start_direction * endpoint_buffer
    end = end - end_direction * endpoint_buffer
    return [
        start,
        np.array([-2.62, -3.18, 0.0]),
        np.array([-3.22, -2.45, 0.0]),
        np.array([-3.34, -0.84, 0.0]),
        np.array([-3.28, 0.92, 0.0]),
        np.array([-3.12, 2.02, 0.0]),
        end,
    ]


def process_recap_points():
    points = list(process_backbone_points())
    if STORY.get("topology_mode") in {"feedback_loop", "cycle_loop"}:
        feedback = process_feedback_points()
        points.extend(feedback[1:])
    return points


def process_travel_path(index):
    path = VMobject()
    path.set_points_smoothly(process_curve_points(index, endpoint_buffer=0.04))
    return path


def tcp_packet_icon(point, color, size=0.18, opacity=0.94, filled=True):
    packet = RoundedRectangle(
        corner_radius=size * 0.16,
        width=size * 1.18,
        height=size,
        stroke_color=color,
        stroke_width=2,
        stroke_opacity=opacity,
        fill_color=color,
        fill_opacity=0.18 if filled else 0.025,
    ).move_to(point)
    seam = Line(
        point + np.array([-size * 0.18, -size * 0.38, 0]),
        point + np.array([-size * 0.18, size * 0.38, 0]),
        color=color,
        stroke_width=1.5,
        stroke_opacity=opacity * 0.72,
    )
    bit = mechanism_dot(
        point + np.array([size * 0.20, 0, 0]),
        color=color,
        radius=size * 0.08,
    )
    bit.set_opacity(opacity)
    return VGroup(packet, seam, bit)


def tcp_role_glyph(point, role, color, seed):
    role = str(role or "TRANSFORM").upper()
    if role == "PROBE":
        return VGroup(
            tcp_packet_icon(point + np.array([-0.09, 0, 0]), color, size=0.13),
            tcp_packet_icon(point + np.array([0.09, 0, 0]), color, size=0.13),
            mechanism_path(
                [
                    point + np.array([-0.25, 0.16, 0]),
                    point + np.array([-0.29, 0.16, 0]),
                    point + np.array([-0.29, -0.16, 0]),
                    point + np.array([-0.25, -0.16, 0]),
                ],
                color=color,
                width=2,
                seed=seed,
                opacity=0.88,
            ),
            mechanism_path(
                [
                    point + np.array([0.25, 0.16, 0]),
                    point + np.array([0.29, 0.16, 0]),
                    point + np.array([0.29, -0.16, 0]),
                    point + np.array([0.25, -0.16, 0]),
                ],
                color=color,
                width=2,
                seed=seed + 1,
                opacity=0.88,
            ),
        )
    if role == "EXPAND":
        packets = [
            tcp_packet_icon(
                point + np.array([(index - 1) * 0.13, -0.03, 0]),
                color,
                size=0.105,
            )
            for index in range(3)
        ]
        packets.append(
            Arrow(
                point + np.array([0.0, 0.12, 0]),
                point + np.array([0.25, 0.12, 0]),
                color=color,
                stroke_width=2,
                buff=0,
                max_tip_length_to_length_ratio=0.36,
            )
        )
        return VGroup(*packets)
    if role == "MODERATE":
        return VGroup(
            mechanism_path(
                [
                    point + np.array([-0.24, -0.14, 0]),
                    point + np.array([-0.08, -0.08, 0]),
                    point + np.array([0.07, 0.01, 0]),
                    point + np.array([0.22, 0.15, 0]),
                ],
                color=color,
                width=3,
                seed=seed,
                opacity=0.94,
            ),
            *[
                mechanism_dot(
                    point + np.array([x, y, 0]),
                    color=color,
                    radius=0.035,
                )
                for x, y in ((-0.24, -0.14), (-0.08, -0.08), (0.07, 0.01), (0.22, 0.15))
            ],
        )
    if role == "ADJUST":
        packet = tcp_packet_icon(point + np.array([-0.10, 0, 0]), color, size=0.15)
        lost = tcp_packet_icon(
            point + np.array([0.13, 0, 0]),
            color,
            size=0.15,
            opacity=0.35,
            filled=False,
        )
        cross = VGroup(
            Line(
                point + np.array([0.04, -0.10, 0]),
                point + np.array([0.22, 0.10, 0]),
                color=color,
                stroke_width=2.5,
            ),
            Line(
                point + np.array([0.04, 0.10, 0]),
                point + np.array([0.22, -0.10, 0]),
                color=color,
                stroke_width=2.5,
            ),
        )
        return VGroup(packet, lost, cross)
    if role == "FEEDBACK":
        return VGroup(
            Arc(
                radius=0.22,
                start_angle=0.05 * PI,
                angle=1.55 * PI,
                color=color,
                stroke_width=3,
            ).move_to(point),
            tiny_label("ACK", point, color=color, size=10),
            Polygon(
                point + np.array([0.16, 0.15, 0]),
                point + np.array([0.26, 0.17, 0]),
                point + np.array([0.20, 0.07, 0]),
                stroke_color=color,
                fill_color=color,
                fill_opacity=0.9,
            ),
        )
    return None


def heat_pump_role_glyph(point, role, color, seed):
    role = str(role or "TRANSFORM").upper()
    if role == "INPUT":
        return VGroup(
            mechanism_path(
                [
                    point + np.array([-0.24, 0.08, 0]),
                    point + np.array([-0.08, 0.14, 0]),
                    point + np.array([0.08, 0.02, 0]),
                    point + np.array([0.24, 0.08, 0]),
                ],
                color=color,
                width=3,
                seed=seed,
                opacity=0.94,
            ),
            Arrow(
                point + np.array([-0.18, -0.12, 0]),
                point + np.array([0.20, -0.12, 0]),
                color=color,
                stroke_width=2,
                buff=0,
                max_tip_length_to_length_ratio=0.30,
            ),
        )
    if role == "ABSORB":
        arrows = [
            Arrow(
                point + direction * 0.30,
                point + direction * 0.11,
                color=color,
                stroke_width=2,
                buff=0,
                max_tip_length_to_length_ratio=0.42,
            )
            for direction in (LEFT, RIGHT, DOWN)
        ]
        vapor = [
            mechanism_dot(
                point + np.array([x, y, 0]),
                color=color,
                radius=radius,
            )
            for x, y, radius in (
                (-0.10, 0.02, 0.045),
                (0.05, 0.10, 0.04),
                (0.14, 0.22, 0.032),
            )
        ]
        return VGroup(*arrows, *vapor)
    if role == "COMPRESS":
        return VGroup(
            Arrow(
                point + np.array([-0.28, 0, 0]),
                point + np.array([-0.09, 0, 0]),
                color=color,
                stroke_width=3,
                buff=0,
                max_tip_length_to_length_ratio=0.42,
            ),
            Arrow(
                point + np.array([0.28, 0, 0]),
                point + np.array([0.09, 0, 0]),
                color=color,
                stroke_width=3,
                buff=0,
                max_tip_length_to_length_ratio=0.42,
            ),
            *[
                mechanism_dot(
                    point + np.array([x, y, 0]),
                    color=color,
                    radius=0.035,
                )
                for x, y in ((-0.05, 0.09), (0.05, 0.01), (-0.02, -0.10))
            ],
        )
    if role == "RELEASE":
        waves = []
        for index, y in enumerate((-0.13, 0.0, 0.13)):
            waves.append(
                mechanism_path(
                    [
                        point + np.array([-0.21, y, 0]),
                        point + np.array([-0.08, y + 0.04, 0]),
                        point + np.array([0.05, y - 0.04, 0]),
                        point + np.array([0.21, y, 0]),
                    ],
                    color=color,
                    width=2,
                    seed=seed + index,
                    opacity=0.92,
                )
            )
        return VGroup(
            mechanism_dot(
                point + np.array([-0.25, 0, 0]),
                color=color,
                radius=0.055,
            ),
            *waves,
        )
    if role == "RETURN":
        valve = VGroup(
            Polygon(
                point + np.array([-0.20, 0.16, 0]),
                point,
                point + np.array([-0.20, -0.16, 0]),
                stroke_color=color,
                stroke_width=2,
                fill_opacity=0,
            ),
            Polygon(
                point + np.array([0.20, 0.16, 0]),
                point,
                point + np.array([0.20, -0.16, 0]),
                stroke_color=color,
                stroke_width=2,
                fill_opacity=0,
            ),
        )
        return VGroup(
            valve,
            Arc(
                radius=0.27,
                start_angle=-0.15 * PI,
                angle=1.35 * PI,
                color=color,
                stroke_width=2,
            ).move_to(point),
            Polygon(
                point + np.array([-0.18, 0.21, 0]),
                point + np.array([-0.28, 0.18, 0]),
                point + np.array([-0.22, 0.10, 0]),
                stroke_color=color,
                fill_color=color,
                fill_opacity=0.9,
            ),
        )
    return None


def process_role_glyph(point, role, color, seed):
    role = str(role or "TRANSFORM").upper()
    if STORY.get("source_visual_profile") == "heat_pump_cycle_v1":
        heat_pump_glyph = heat_pump_role_glyph(
            point,
            role,
            color,
            seed,
        )
        if heat_pump_glyph is not None:
            return heat_pump_glyph
    if STORY.get("source_visual_profile") == "tcp_congestion_control_v1":
        tcp_glyph = tcp_role_glyph(point, role, color, seed)
        if tcp_glyph is not None:
            return tcp_glyph
    if role == "PROBE":
        return VGroup(
            *[
                Arc(
                    radius=radius,
                    start_angle=-0.72 * PI,
                    angle=1.44 * PI,
                    color=color,
                    stroke_width=max(2, 4 - index),
                    stroke_opacity=0.94 - index * 0.18,
                ).move_to(point)
                for index, radius in enumerate((0.09, 0.18, 0.27))
            ],
            mechanism_dot(point, color=color, radius=0.035),
        )
    if role == "EXPAND":
        arrows = []
        for direction in (UP, RIGHT, DOWN, LEFT):
            arrows.append(
                Arrow(
                    point + direction * 0.04,
                    point + direction * 0.24,
                    color=color,
                    stroke_width=2,
                    buff=0,
                    max_tip_length_to_length_ratio=0.42,
                )
            )
        return VGroup(*arrows)
    if role == "MODERATE":
        arc = Arc(
            radius=0.22,
            start_angle=0.12 * PI,
            angle=0.76 * PI,
            color=color,
            stroke_width=3,
        ).move_to(point)
        needle = Line(
            point,
            point + np.array([0.12, 0.12, 0]),
            color=color,
            stroke_width=3,
        )
        return VGroup(arc, needle, mechanism_dot(point, color=color, radius=0.035))
    if role == "ADJUST":
        return VGroup(
            *[
                Line(
                    point + np.array([-0.22, y, 0]),
                    point + np.array([0.22, y, 0]),
                    color=color,
                    stroke_width=2,
                    stroke_opacity=0.86,
                )
                for y in (-0.13, 0.0, 0.13)
            ],
            mechanism_dot(point + np.array([-0.08, -0.13, 0]), color=color, radius=0.045),
            mechanism_dot(point + np.array([0.10, 0.0, 0]), color=color, radius=0.045),
            mechanism_dot(point + np.array([-0.02, 0.13, 0]), color=color, radius=0.045),
        )
    if role == "FEEDBACK":
        return VGroup(
            Arc(
                radius=0.21,
                start_angle=0.12 * PI,
                angle=1.58 * PI,
                color=color,
                stroke_width=3,
            ).move_to(point),
            Polygon(
                point + np.array([0.16, 0.15, 0]),
                point + np.array([0.26, 0.17, 0]),
                point + np.array([0.20, 0.07, 0]),
                stroke_color=color,
                fill_color=color,
                fill_opacity=0.9,
            ),
        )
    if role == "LOOKUP":
        lens = mechanism_circle(
            point + np.array([-0.035, 0.035, 0]),
            0.14,
            color=color,
            width=3,
            seed=seed,
            opacity=0.94,
        )
        handle = mechanism_path(
            [
                point + np.array([0.07, -0.07, 0]),
                point + np.array([0.22, -0.22, 0]),
            ],
            color=color,
            width=3,
            seed=seed + 1,
            opacity=0.94,
        )
        return VGroup(lens, handle)
    if role == "DISPATCH":
        shaft = mechanism_path(
            [
                point + np.array([-0.20, 0, 0]),
                point + np.array([0.14, 0, 0]),
            ],
            color=color,
            width=4,
            seed=seed,
            opacity=0.94,
        )
        head = Polygon(
            point + np.array([0.21, 0, 0]),
            point + np.array([0.06, 0.11, 0]),
            point + np.array([0.06, -0.11, 0]),
            stroke_color=color,
            stroke_width=2,
            fill_color=color,
            fill_opacity=0.88,
        )
        return VGroup(shaft, head)
    if role == "ROUTE":
        return VGroup(
            mechanism_path(
                [
                    point + np.array([-0.18, 0, 0]),
                    point,
                    point + np.array([0.18, 0.15, 0]),
                ],
                color=color,
                width=3,
                seed=seed,
                opacity=0.94,
            ),
            mechanism_path(
                [
                    point,
                    point + np.array([0.18, -0.15, 0]),
                ],
                color=color,
                width=3,
                seed=seed + 1,
                opacity=0.94,
            ),
            mechanism_dot(point, color=color, radius=0.045),
        )
    if role == "VERIFY":
        diamond = Polygon(
            point + np.array([0, 0.22, 0]),
            point + np.array([0.22, 0, 0]),
            point + np.array([0, -0.22, 0]),
            point + np.array([-0.22, 0, 0]),
            stroke_color=color,
            stroke_width=3,
            fill_opacity=0,
        )
        check = mechanism_path(
            [
                point + np.array([-0.10, 0, 0]),
                point + np.array([-0.02, -0.08, 0]),
                point + np.array([0.12, 0.10, 0]),
            ],
            color=color,
            width=3,
            seed=seed,
            opacity=0.94,
        )
        return VGroup(diamond, check)
    if role == "STORE":
        box = RoundedRectangle(
            corner_radius=0.06,
            width=0.42,
            height=0.32,
            stroke_color=color,
            stroke_width=3,
            fill_opacity=0,
        ).move_to(point)
        drawer = mechanism_path(
            [
                point + np.array([-0.15, 0.03, 0]),
                point + np.array([0.15, 0.03, 0]),
            ],
            color=color,
            width=3,
            seed=seed,
            opacity=0.9,
        )
        return VGroup(box, drawer, mechanism_dot(point + np.array([0, -0.08, 0]), color=color, radius=0.025))
    if role in {"RESOLVE", "OUTPUT"}:
        return VGroup(
            mechanism_circle(point, 0.18, color=color, width=3, seed=seed, opacity=0.94),
            mechanism_dot(point, color=color, radius=0.065),
            *[
                Line(
                    point + direction * 0.23,
                    point + direction * 0.31,
                    color=color,
                    stroke_width=2,
                    stroke_opacity=0.86,
                )
                for direction in (UP, RIGHT, DOWN, LEFT)
            ],
        )
    if role == "INPUT":
        return VGroup(
            Arc(radius=0.20, start_angle=-0.65 * PI, angle=1.3 * PI, color=color, stroke_width=3).move_to(point),
            mechanism_dot(point + np.array([0.05, 0, 0]), color=color, radius=0.045),
        )
    return gear(point, 0.20, color, teeth=8)


def tcp_window_state(stage):
    stage = min(max(0, int(stage)), 4)
    center = np.array([-0.42, 3.36, 0.0])
    filled_counts = (2, 4, 5, 2, 3)
    status_labels = (
        "PROBE CAPACITY",
        "ACKS EXPAND",
        "ONE PER RTT",
        "LOSS • SHRINK",
        "ACKS • REPEAT",
    )
    filled_count = filled_counts[stage]
    packet_centers = [
        center + np.array([(index - 2) * 0.40, 0, 0])
        for index in range(5)
    ]
    items = [
        tiny_label(
            "CONGESTION WINDOW",
            center + np.array([0.42, 0.36, 0]),
            color=P["ink"],
            size=15,
        ),
        tiny_label(
            status_labels[stage],
            center + np.array([1.76, 0.0, 0]),
            color=story_color(stage),
            size=13,
        ),
        mechanism_path(
            [
                center + np.array([-1.08, 0.22, 0]),
                center + np.array([-1.16, 0.22, 0]),
                center + np.array([-1.16, -0.22, 0]),
                center + np.array([-1.08, -0.22, 0]),
            ],
            color=P["muted"],
            width=2,
            seed=725,
            opacity=0.62,
        ),
        mechanism_path(
            [
                center + np.array([1.08, 0.22, 0]),
                center + np.array([1.16, 0.22, 0]),
                center + np.array([1.16, -0.22, 0]),
                center + np.array([1.08, -0.22, 0]),
            ],
            color=P["muted"],
            width=2,
            seed=726,
            opacity=0.62,
        ),
    ]
    for index, packet_center in enumerate(packet_centers):
        filled = index < filled_count
        items.append(
            tcp_packet_icon(
                packet_center,
                story_color(stage) if filled else P["muted"],
                size=0.27,
                opacity=0.92 if filled else 0.22,
                filled=filled,
            )
        )
    if stage >= 2:
        threshold_x = center[0] + 0.60
        items.extend(
            [
                DashedLine(
                    [threshold_x, center[1] - 0.25, 0],
                    [threshold_x, center[1] + 0.25, 0],
                    color=P["c"],
                    stroke_width=2,
                    stroke_opacity=0.68,
                    dash_length=0.055,
                )
            ]
        )
    if stage == 3:
        lost_point = packet_centers[-1]
        items.extend(
            [
                Line(
                    lost_point + np.array([-0.10, -0.10, 0]),
                    lost_point + np.array([0.10, 0.10, 0]),
                    color=P["b"],
                    stroke_width=2.5,
                ),
                Line(
                    lost_point + np.array([-0.10, 0.10, 0]),
                    lost_point + np.array([0.10, -0.10, 0]),
                    color=P["b"],
                    stroke_width=2.5,
                ),
            ]
        )
    return VGroup(*items)


def process_carrier(point, color, seed):
    if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
        return VGroup(
            mechanism_circle(point, 0.49, color=color, width=4, seed=seed, opacity=0.9),
            Arc(
                radius=0.60,
                start_angle=0.14 * PI,
                angle=0.92 * PI,
                color=color,
                stroke_width=2,
                stroke_opacity=0.44,
            ).move_to(point),
            mechanism_dot(point + np.array([0.47, 0.11, 0]), color=color, radius=0.045),
        )
    return VGroup(
        Circle(radius=0.50, stroke_color=color, stroke_width=3, stroke_opacity=0.9).move_to(point),
        Arc(
            radius=0.61,
            start_angle=-0.25 * PI,
            angle=1.42 * PI,
            color=color,
            stroke_width=2,
            stroke_opacity=0.36,
        ).move_to(point),
        Dot(point + np.array([0.48, -0.11, 0]), radius=0.04, color=color),
    )


def heat_pump_refrigerant_token(point, color, seed):
    return VGroup(
        mechanism_dot(point, color=color, radius=0.11),
        mechanism_circle(
            point,
            0.20,
            color=color,
            width=3,
            seed=seed,
            opacity=0.66,
        ),
        *[
            mechanism_dot(
                point + np.array([x, y, 0]),
                color=color,
                radius=0.035,
            )
            for x, y in ((-0.18, 0.12), (0.16, 0.14), (0.18, -0.12))
        ],
    )


def causal_explainer_visual(stage):
    visual = VGroup()
    positions = process_positions()
    label_positions = process_label_positions()
    visible_count = min(stage + 1, len(STORY_STAGES), len(positions))
    tcp_profile = (
        STORY.get("source_visual_profile")
        == "tcp_congestion_control_v1"
    )
    heat_pump_profile = (
        STORY.get("source_visual_profile")
        == "heat_pump_cycle_v1"
    )
    core_parts = [
        tiny_label(
            "ONE QUESTION • ONE CONTINUOUS JOURNEY",
            [0, 4.05, 0],
            color=P["muted"],
            size=16,
        )
    ]
    if not tcp_profile:
        core_parts.append(
            story_label(
                STORY.get("core_label", "THE MECHANISM"),
                [0, 3.62, 0],
                max_width=6.4,
                max_height=0.62,
                chars=28,
                lines=1,
                size=28,
                color=P["ink"],
            )
        )
    if heat_pump_profile:
        core_parts.extend(
            [
                tiny_label(
                    "COLD • LOW PRESSURE",
                    [-2.35, 3.18, 0],
                    color=P["a"],
                    size=13,
                ),
                mechanism_arrow(
                    [-1.25, 3.18, 0],
                    [1.18, 3.18, 0],
                    color=P["muted"],
                    width=2,
                    seed=591,
                    opacity=0.58,
                ),
                tiny_label(
                    "HOT • HIGH PRESSURE",
                    [2.30, 3.18, 0],
                    color=P["b"],
                    size=13,
                ),
            ]
        )
    visual.add(semantic_part("causal_core", *core_parts))
    if tcp_profile:
        visual.add(
            semantic_part(
                "tcp_window_state",
                tcp_window_state(stage),
            )
        )
    visual.add(
        semantic_part(
            "process_backbone",
            mechanism_path(
                process_backbone_points(),
                color=P["muted"],
                width=2,
                seed=602,
                opacity=0.19,
            ),
            mechanism_dot(positions[0], color=P["muted"], radius=0.028),
            mechanism_dot(positions[-1], color=P["muted"], radius=0.028),
        )
    )

    for index in range(1, visible_count):
        points = process_curve_points(index, endpoint_buffer=0.46)
        color = story_color(index)
        visual.add(
            semantic_part(
                f"process_link_{index}",
                mechanism_path(
                    points,
                    color=color,
                    width=5 if index == stage else 3,
                    seed=610 + index,
                    opacity=0.90 if index == stage else 0.54,
                ),
                mechanism_dot(
                    points[len(points) // 2],
                    color=color,
                    radius=0.045,
                ),
            )
        )

    for index in range(visible_count):
        point = positions[index]
        color = story_color(index)
        active = index == stage
        stage_data = story_stage(index)
        mechanism_role = stage_data.get("mechanism_role", "TRANSFORM")
        station = VGroup(
            mechanism_circle(
                point,
                0.34,
                color=color,
                width=4 if active else 3,
                seed=640 + index,
                opacity=0.94 if active else 0.68,
            ),
            process_role_glyph(point, mechanism_role, color, 660 + index * 5),
            mechanism_path(
                [
                    point + np.array([-0.38, 0.23, 0]),
                    point + np.array([-0.13, 0.43, 0]),
                    point + np.array([0.18, 0.42, 0]),
                    point + np.array([0.41, 0.19, 0]),
                    point + np.array([0.45, -0.12, 0]),
                ],
                color=color,
                width=2,
                seed=648 + index,
                opacity=0.38 if active else 0.23,
            ),
            tiny_label(str(index + 1), point + np.array([-0.53, 0.35, 0]), color=color, size=14),
        )
        label_point = label_positions[index]
        label = story_label(
            stage_data.get("label", "NEXT STEP"),
            label_point,
            max_width=3.85 if index < 4 else 3.55,
            max_height=0.74,
            chars=24,
            lines=2,
            size=22 if active else 19,
            color=P["ink"] if active else color,
            complete=True,
        )
        role_offset = np.array([-0.58, 0.56, 0]) if point[0] < 0 else np.array([0.58, 0.56, 0])
        visual.add(
            semantic_part(
                f"process_station_{index}",
                station,
                label,
                tiny_label(
                    str(mechanism_role).replace("_", " ").lower(),
                    point + role_offset,
                    color=color,
                    size=14,
                ),
            )
        )
        if active:
            visual.add(
                semantic_part(
                    "process_carrier",
                    process_carrier(point, color, 700 + index),
                )
            )
            if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
                underline_half_width = 1.55 if index < 4 else 1.36
                active_mark = mechanism_path(
                    [
                        label_point + np.array([-underline_half_width, -0.48, 0]),
                        label_point + np.array([-underline_half_width * 0.5, -0.53, 0]),
                        label_point + np.array([0, -0.47, 0]),
                        label_point + np.array([underline_half_width * 0.5, -0.53, 0]),
                        label_point + np.array([underline_half_width, -0.47, 0]),
                    ],
                    color=color,
                    width=4,
                    seed=670 + index,
                    opacity=0.9,
                )
            else:
                active_mark = Arc(
                    radius=0.56,
                    start_angle=0.06 * PI,
                    angle=1.6 * PI,
                    color=color,
                    stroke_width=3,
                    stroke_opacity=0.72,
                ).move_to(point)
            visual.add(semantic_part("active_step", active_mark))

    if stage >= len(STORY_STAGES) - 1 and visible_count > 1:
        topology_mode = STORY.get("topology_mode")
        loop_return = topology_mode in {"feedback_loop", "cycle_loop"}
        feedback_loop = topology_mode == "feedback_loop"
        cycle_loop = topology_mode == "cycle_loop"
        if loop_return:
            visual.add(
                semantic_part(
                    "process_feedback_return",
                    mechanism_path(
                        process_feedback_points(endpoint_buffer=0.38),
                        color=P["b"],
                        width=4,
                        seed=694,
                        opacity=0.48,
                    ),
                    tiny_label(
                        "CYCLE" if cycle_loop else "FEEDBACK",
                        [-3.08, -0.58, 0],
                        color=P["c"] if cycle_loop else P["b"],
                        size=14,
                        rotation=PI / 2,
                    ),
                )
            )
        visual.add(
            semantic_part(
                "causal_payoff",
                mechanism_path(
                    [[-2.7, -3.72, 0], [-1.35, -3.64, 0], [0, -3.75, 0], [1.35, -3.65, 0], [2.7, -3.72, 0]],
                    color=P["c"],
                    width=4,
                    seed=699,
                    opacity=0.82,
                ),
                tiny_label(
                    (
                        "PROBE → ADJUST → PROBE AGAIN"
                        if feedback_loop
                        else (
                            str(
                                story_stage(
                                    len(STORY_STAGES) - 1
                                ).get("mechanism_role", "RETURN")
                            )
                            + " → "
                            + str(
                                story_stage(
                                    int(
                                        (
                                            STORY.get(
                                                "cycle_contract",
                                                {},
                                            )
                                        ).get(
                                            "return_to_stage_index",
                                            0,
                                        )
                                        or 0
                                    )
                                ).get(
                                    "mechanism_role",
                                    "INPUT",
                                )
                            )
                            + " • CYCLE REPEATS"
                        )
                        if cycle_loop
                        else (
                            str(story_stage(0).get("mechanism_role", "INPUT"))
                            + " → "
                            + str(
                                story_stage(len(STORY_STAGES) - 1).get(
                                    "mechanism_role",
                                    "OUTPUT",
                                )
                            )
                            + " • ONE CONTINUOUS PATH"
                        )
                    ),
                    [0, -4.08, 0],
                    color=P["c"],
                    size=17,
                ),
            )
        )
    return visual


def generic_whiteboard_visual(stage):
    visual = VGroup()
    center = np.array([0.0, 0.15, 0.0])
    core_color = P["a"]
    visual.add(ink_circle(center, 1.08, color=core_color, width=6, seed=201))
    visual.add(
        story_label(
            STORY.get("core_label", "THE IDEA"),
            center,
            max_width=1.72,
            max_height=0.96,
            chars=11,
            lines=3,
            size=25,
        )
    )
    visual.add(tiny_label(story_stage(0).get("role", "HOOK"), [0, 1.7, 0], color=P["b"], size=22, rotation=-0.025))
    positions = (
        np.array([-2.65, 2.25, 0.0]),
        np.array([2.65, 2.05, 0.0]),
        np.array([-2.65, -2.2, 0.0]),
        np.array([2.65, -2.35, 0.0]),
    )
    for index in range(1, min(stage + 1, len(STORY_STAGES))):
        point = positions[index - 1]
        color = story_color(index - 1)
        direction = normalize(point - center)
        start = center + direction * 1.08
        end = point - direction * 0.72
        perpendicular = np.array([-direction[1], direction[0], 0.0])
        visual.add(
            ink_path(
                [start, interpolate(start, end, 0.52) + perpendicular * (0.16 if index % 2 else -0.16), end],
                color=color,
                width=4,
                seed=210 + index,
            )
        )
        visual.add(ink_circle(point, 0.7, color=color, width=4, seed=220 + index))
        visual.add(story_label(story_stage(index).get("label", "NEXT IDEA"), point, color=color))
        role_y = point[1] + (0.92 if point[1] > 0 else -0.92)
        visual.add(tiny_label(story_stage(index).get("role", "CLAIM"), [point[0], role_y, 0], color=P["muted"], size=16))
    if stage >= len(STORY_STAGES) - 1 and len(STORY_STAGES) > 1:
        visual.add(
            ink_path(
                [[-1.45, -3.55, 0], [-0.45, -3.72, 0], [0.55, -3.5, 0], [1.55, -3.65, 0]],
                color=P["c"],
                width=5,
                seed=249,
            )
        )
        visual.add(tiny_label("ONE CONNECTED EXPLANATION", [0, -4.05, 0], color=P["c"], size=19, rotation=0.015))
    return visual


def generic_papyrus_visual(stage):
    visual = VGroup()
    center = np.array([0.0, 0.1, 0.0])
    visual.add(ink_circle(center, 1.16, color=P["b"], width=5, seed=260))
    visual.add(gear(center, 0.8, P["c"], teeth=12))
    visual.add(
        story_label(
            STORY.get("core_label", "THE IDEA"),
            center,
            max_width=1.62,
            max_height=0.92,
            chars=10,
            lines=3,
            size=23,
        )
    )
    visual.add(tiny_label(story_stage(0).get("role", "HOOK"), [0, 1.72, 0], color=P["a"], size=20, rotation=-0.015))
    positions = (
        np.array([-2.7, 2.2, 0.0]),
        np.array([2.7, 2.05, 0.0]),
        np.array([-2.65, -2.25, 0.0]),
        np.array([2.65, -2.35, 0.0]),
    )
    for index in range(1, min(stage + 1, len(STORY_STAGES))):
        point = positions[index - 1]
        color = story_color(index - 1)
        visual.add(ink_line(center, point, color=P["muted"], width=3, seed=270 + index, opacity=0.65))
        visual.add(gear(point, 0.43, color, teeth=8))
        label_y = point[1] - (0.78 if point[1] > 0 else -0.78)
        role_y = point[1] + (0.74 if point[1] > 0 else -0.74)
        visual.add(
            story_label(
                story_stage(index).get("label", "NEXT IDEA"),
                [point[0], label_y, 0],
                max_width=1.85,
                max_height=0.62,
                chars=13,
                size=21,
                color=color,
            )
        )
        visual.add(tiny_label(story_stage(index).get("role", "CLAIM"), [point[0], role_y, 0], color=P["muted"], size=15))
    if stage >= len(STORY_STAGES) - 1 and len(STORY_STAGES) > 1:
        visual.add(Arc(radius=3.12, start_angle=PI * 1.1, angle=PI * 0.8, color=P["a"], stroke_width=4).shift(DOWN * 0.55))
        visual.add(tiny_label("THE MECHANISM CLOSES", [0, -4.1, 0], color=P["a"], size=20, rotation=-0.015))
    return visual


def generic_future_visual(stage):
    visual = VGroup()
    center = np.array([0.0, 0.1, 0.0])
    visual.add(Circle(radius=1.12, stroke_color=P["a"], stroke_width=2, stroke_opacity=0.4).move_to(center))
    visual.add(Circle(radius=0.92, stroke_color=P["a"], stroke_width=5, stroke_opacity=0.95).move_to(center))
    visual.add(
        story_label(
            STORY.get("core_label", "THE IDEA"),
            center,
            max_width=1.55,
            max_height=0.9,
            chars=10,
            lines=3,
            size=22,
        )
    )
    visual.add(tiny_label(story_stage(0).get("role", "HOOK") + " // CORE", [0, 1.72, 0], color=P["a"], size=18))
    positions = (
        np.array([-2.75, 2.15, 0.0]),
        np.array([2.75, 2.0, 0.0]),
        np.array([-2.7, -2.25, 0.0]),
        np.array([2.7, -2.35, 0.0]),
    )
    for index in range(1, min(stage + 1, len(STORY_STAGES))):
        point = positions[index - 1]
        color = story_color(index - 1)
        visual.add(Line(center, point, color=color, stroke_width=2, stroke_opacity=0.55))
        visual.add(Circle(radius=0.52, stroke_color=color, stroke_width=3, stroke_opacity=0.9).move_to(point))
        visual.add(Circle(radius=0.64, stroke_color=color, stroke_width=1, stroke_opacity=0.22).move_to(point))
        visual.add(Dot(point, radius=0.065, color=color))
        label_y = point[1] - (0.86 if point[1] > 0 else -0.86)
        role_y = point[1] + (0.72 if point[1] > 0 else -0.72)
        visual.add(
            story_label(
                story_stage(index).get("label", "NEXT IDEA"),
                [point[0], label_y, 0],
                max_width=1.95,
                max_height=0.58,
                chars=14,
                size=19,
                color=color,
            )
        )
        visual.add(tiny_label(story_stage(index).get("role", "CLAIM"), [point[0], role_y, 0], color=P["muted"], size=14))
    if stage >= len(STORY_STAGES) - 1 and len(STORY_STAGES) > 1:
        for radius, opacity in ((2.65, 0.24), (3.0, 0.12)):
            visual.add(Arc(radius=radius, start_angle=PI * 1.12, angle=PI * 0.76, color=P["c"], stroke_width=2, stroke_opacity=opacity).shift(DOWN * 0.3))
        visual.add(tiny_label("MODEL COMPLETE // SOURCE LOCKED", [0, -4.1, 0], color=P["c"], size=18))
    return visual


def generic_director_visual(stage):
    visual = VGroup()
    core = story_label(
        STORY.get("core_label", "THE IDEA"),
        [0, 2.78, 0],
        max_width=5.4,
        max_height=0.95,
        chars=24,
        size=35,
        color=P["c"],
    )
    visual.add(core)
    visual.add(Line([-2.5, 2.28, 0], [2.5, 2.28, 0], color=P["c"], stroke_width=4, stroke_opacity=0.7))
    visual.add(tiny_label(story_stage(0).get("role", "HOOK") + " / SOURCE MAP", [0, 1.92, 0], color=P["muted"], size=17))
    y_positions = (1.05, -0.15, -1.35, -2.55)
    for index in range(1, min(stage + 1, len(STORY_STAGES))):
        y = y_positions[index - 1]
        color = story_color(index - 1)
        visual.add(Line([-3.25, y, 0], [-2.0, y, 0], color=color, stroke_width=6, stroke_opacity=0.82))
        visual.add(Line([2.0, y, 0], [3.25, y, 0], color=color, stroke_width=6, stroke_opacity=0.82))
        visual.add(Dot([-3.45, y, 0], radius=0.075, color=color))
        visual.add(
            story_label(
                story_stage(index).get("label", "NEXT IDEA"),
                [0, y, 0],
                max_width=3.7,
                max_height=0.66,
                chars=20,
                size=25,
                color=P["ink"],
            )
        )
        visual.add(tiny_label(story_stage(index).get("role", "CLAIM"), [-3.1, y + 0.34, 0], color=color, size=14))
    if stage >= len(STORY_STAGES) - 1 and len(STORY_STAGES) > 1:
        visual.add(
            ArcBetweenPoints(
                [-3.42, 1.05, 0],
                [-3.42, -2.55, 0],
                angle=0.18,
                color=P["c"],
                stroke_width=3,
            )
        )
        visual.add(fit_text("ONE STORY", max_width=2.2, size=24, color=P["c"], weight=BOLD).move_to([0, -3.65, 0]))
    return visual


def stage_visual(stage, phase=0):
    if STORY.get("kind") == "technology_adolescence":
        return technology_adolescence_visual(stage, phase=phase)
    if STORY.get("kind") == "mechanism_orbit":
        return mechanism_orbit_visual(stage)
    if STORY.get("kind") == "mechanism_gradient":
        return mechanism_gradient_visual(stage)
    if STORY.get("kind") == "mechanism_attention":
        return mechanism_attention_visual(stage)
    if STORY.get("kind") == "mechanism_bayes":
        return mechanism_bayes_visual(stage, phase=phase)
    if STORY.get("kind") == "mechanism_handshake":
        return mechanism_handshake_visual(stage)
    if STORY.get("kind") == "causal_explainer":
        return causal_explainer_visual(stage)
    if STORY.get("kind") != "open_weights_debate":
        if STYLE == "whiteboard":
            return generic_whiteboard_visual(stage)
        if STYLE == "warm_papyrus":
            return generic_papyrus_visual(stage)
        if STYLE == "future_minimal":
            return generic_future_visual(stage)
        return generic_director_visual(stage)
    if STYLE == "whiteboard":
        return whiteboard_visual(stage)
    if STYLE == "warm_papyrus":
        return papyrus_visual(stage)
    if STYLE == "future_minimal":
        return future_visual(stage)
    return director_visual(stage)


def caption_text(value):
    caption = wrap_text(value, max_width=7.25, max_height=0.92, chars=28, lines=2, size=34, color=P["ink"], weight=BOLD)
    caption.move_to(DOWN * 5.92)
    return caption


def headline_text(value):
    title = complete_wrap_text(
        value,
        max_width=7.5,
        max_height=1.45,
        chars=30,
        lines=3,
        size=46,
        color=P["ink"],
        weight=BOLD,
    )
    title.move_to(UP * 5.78)
    return title


def narration_visual_phase(stage, caption):
    kind = STORY.get("kind")
    if kind == "technology_adolescence":
        text = caption.lower()
        if stage == 0:
            if any(term in text for term in ("maturity", "wield it")):
                return 2
            if any(term in text for term in ("humanity", "enormous power", "gaining")):
                return 1
        if stage == 1:
            if any(term in text for term in ("faster", "than humans")):
                return 3
            if any(term in text for term in ("millions", "copies")):
                return 2
            if any(term in text for term in ("country of geniuses", "datacenter", "powerful ai")):
                return 1
        if stage == 2:
            if "economic" in text:
                return 4
            if "political" in text:
                return 3
            if any(term in text for term in ("destructive", "misuse")):
                return 2
            if any(term in text for term in ("four tests", "autonomy")):
                return 1
        if stage == 3:
            if any(term in text for term in ("surgically", "intervene", "targeted")):
                return 4
            if "defense" in text:
                return 3
            if "evidence" in text:
                return 2
            if any(term in text for term in ("uncertainty", "panic", "denial")):
                return 1
        if stage >= 4:
            if any(term in text for term in ("real question", "grow up", "guide it")):
                return 2
            if any(term in text for term in ("adolescence", "rite of passage")):
                return 1
        return 0
    if kind != "mechanism_bayes":
        return 0
    text = caption.lower()
    if stage == 2 and ("multipl" in text or "prior probability by" in text):
        return 1
    if stage == 3 and ("normaliz" in text or "posterior probability" in text):
        return 1
    return 0


def narration_visual_emphasis(visual, caption):
    kind = STORY.get("kind")
    if kind not in {
        "open_weights_debate",
        "causal_explainer",
        "mechanism_bayes",
        "mechanism_orbit",
        "mechanism_gradient",
        "mechanism_attention",
        "mechanism_handshake",
    }:
        return None
    parts = semantic_parts(visual)
    text = caption.lower()
    targets = []

    def add(target, color):
        if target is None or any(existing is target for existing, _color in targets):
            return
        targets.append((target, color))

    def first_available(*keys):
        for key in keys:
            target = parts.get(key)
            if target is not None:
                return target
        return None

    if kind == "open_weights_debate":
        if any(term in text for term in ("nvidia", "amodei", "opposed", "they aren't", "real fight", "frontier risk", "versus closed")):
            add(parts.get("framing"), P["c"])
            add(parts.get("open_weights_core"), P["a"])
        if "weights" in text:
            add(parts.get("open_weights_core"), P["a"])
        if any(term in text for term in ("access", "competition", "control", "customers", "downloadable")):
            add(parts.get("shared_benefits"), P["a"])
        if any(term in text for term in ("released", "pull them back", "withdraw", "no undo", "catch", "transparency", "inspect", "strengthen")):
            add(parts.get("irreversibility"), P["b"])
            add(parts.get("open_weights_core"), P["a"])
        if any(term in text for term in ("defender", "attacker", "gains more")):
            add(parts.get("attacker_defender"), P["c"])
        if any(term in text for term in ("ban", "instead", "restrict", "chip", "distill", "test capable", "open and closed")):
            add(parts.get("policy_response"), P["a"])
    elif kind == "causal_explainer":
        active = parts.get("active_step")
        if active is not None:
            add(active, P["c"])
        if (
            STORY.get("source_visual_profile")
            == "tcp_congestion_control_v1"
            and any(
                term in text
                for term in (
                    "tcp",
                    "window",
                    "in-flight",
                    "in flight",
                    "ack",
                    "threshold",
                    "round trip",
                    "loss",
                    "capacity",
                    "congestion",
                )
            )
        ):
            add(parts.get("tcp_window_state"), P["c"])
        step_indices = sorted(
            int(key.rsplit("_", 1)[-1])
            for key in parts
            if key.startswith("process_station_") and key.rsplit("_", 1)[-1].isdigit()
        )
        if step_indices:
            current_index = step_indices[-1]
            add(parts.get("process_carrier"), story_color(current_index))
            add(parts.get(f"process_station_{current_index}"), story_color(current_index))
            add(parts.get(f"process_link_{current_index}"), story_color(current_index))
    elif kind == "mechanism_handshake":
        if "client" in text or "clienthello" in text or "client hello" in text:
            add(parts.get("client_actor"), P["a"])
            add(parts.get("hello_messages"), P["a"])
        if "server" in text or "serverhello" in text or "server hello" in text:
            add(parts.get("server_actor"), P["b"])
            add(parts.get("hello_messages"), P["b"])
        if any(term in text for term in ("offer", "supported", "protocol", "parameters", "includes")):
            add(parts.get("hello_messages"), P["a"])
        if any(term in text for term in ("key share", "share", "establish", "keying", "keys", "exchanged", "peer", "derive", "same", "secret", "network", "computed keys")):
            add(first_available("shared_secrets", "key_exchange"), P["c"])
            add(parts.get("channel_backbone"), P["muted"])
        if any(term in text for term in ("message", "select", "encrypted")):
            add(parts.get("encrypted_tunnel"), P["c"])
            add(parts.get("hello_messages"), P["a"])
        if any(term in text for term in ("certificate", "signature", "authenticate")):
            add(parts.get("certificate_auth"), P["b"])
            add(parts.get("server_actor"), P["b"])
        if any(term in text for term in ("finished", "transcript", "incorrect", "correct", "terminate", "connection", "validate")):
            add(first_available("finished_checks", "transcript"), P["a"])
        if any(term in text for term in ("both sides", "established", "application data", "traffic keys", "protect")):
            add(first_available("application_data", "encrypted_tunnel"), P["c"])
            add(parts.get("payoff"), P["c"])
    elif kind == "mechanism_bayes":
        hypotheses = parts.get("hypotheses")
        bars = parts.get("probability_bars")
        fair_named = "fair" in text
        trick_named = "trick" in text
        if fair_named:
            add(hypotheses[2] if hypotheses and len(hypotheses) > 2 else hypotheses, P["a"])
            add(bars[0] if bars and len(bars) > 0 else bars, P["a"])
        if trick_named:
            add(hypotheses[3] if hypotheses and len(hypotheses) > 3 else hypotheses, P["c"])
            add(bars[1] if bars and len(bars) > 1 else bars, P["c"])
        if "heads" in text:
            add(first_available("evidence", "hypotheses"), P["b"])
        if not fair_named and not trick_named and ("coin" in text or "which" in text):
            add(hypotheses, P["ink"])
        if not fair_named and not trick_named and any(term in text for term in ("prior", "odds", "fifty")):
            add(bars, P["a"])
        if any(term in text for term in ("likelihood", "predicted")):
            add(first_available("likelihoods", "probability_bars"), P["b"])
        if "weight" in text and "normaliz" not in text:
            add(bars, P["ink"])
        if any(term in text for term in ("posterior", "reweight")):
            add(first_available("payoff", "probability_bars"), P["c"])
    elif kind == "mechanism_orbit":
        if "earth" in text:
            add(parts.get("earth"), P["a"])
        if "satellite" in text:
            add(parts.get("satellite"), P["c"])
        if any(term in text for term in ("gravity", "pull", "fall", "down")):
            add(parts.get("gravity"), P["b"])
        if any(term in text for term in ("sideways", "velocity")):
            add(first_available("velocity", "satellite"), P["c"])
        if "speed" in text:
            add(first_available("speed_paths", "velocity"), P["c"])
        if any(term in text for term in ("orbit", "curve", "path", "trajectory")):
            add(first_available("closed_orbit", "gravity"), P["a"])
        if "thrust" in text:
            add(first_available("payoff", "closed_orbit"), P["c"])
    elif kind == "mechanism_gradient":
        if any(term in text for term in ("loss", "curve")):
            add(parts.get("loss_curve"), P["a"])
        if any(term in text for term in ("gradient", "uphill", "slope", "opposite")):
            add(first_available("gradient_direction", "loss_curve"), P["b"])
        if any(term in text for term in ("step", "recalculate", "repeat", "update")):
            add(first_available("iterative_steps", "starting_point"), P["c"])
        if any(term in text for term in ("learning rate", "overshoot")):
            add(first_available("learning_rate", "iterative_steps"), P["b"])
        if any(term in text for term in ("minimum", "lower")):
            add(first_available("payoff", "loss_curve"), P["c"])
        if any(term in text for term in ("model", "current")):
            add(parts.get("starting_point"), P["b"])
    elif kind == "mechanism_attention":
        if "token" in text:
            add(parts.get("tokens"), P["a"])
        if "query" in text:
            add(first_available("target_query", "key_scores"), P["c"])
        if any(term in text for term in ("key", "score")):
            add(first_available("key_scores", "target_query"), P["b"])
        if any(term in text for term in ("softmax", "weight")):
            add(first_available("softmax_weights", "key_scores"), P["c"])
        if any(term in text for term in ("value", "context", "combine", "weighted")):
            add(first_available("context_output", "softmax_weights"), P["a"])
        if any(term in text for term in ("head", "relationship")):
            add(first_available("multiple_heads", "tokens"), P["b"])
    if not targets:
        return None

    def style_native_emphasis(target):
        if STYLE == "hand_drawn":
            return Wiggle(
                target,
                scale_value=1.07,
                rotation_angle=0.022 * TAU,
                n_wiggles=2,
            )
        if STYLE == "whiteboard":
            tcp_profile = (
                STORY.get("source_visual_profile")
                == "tcp_congestion_control_v1"
            )
            open_weights_profile = STORY.get("kind") == "open_weights_debate"
            if open_weights_profile and target.submobjects:
                trace_index = (
                    1
                    if (
                        target is parts.get("framing")
                        or target is parts.get("policy_response")
                    )
                    and len(target.submobjects) > 1
                    else 0
                )
                marker_trace = (
                    target.submobjects[trace_index]
                    .copy()
                    .set_stroke(
                        color=P["a"],
                        width=9,
                        opacity=0.92,
                    )
                )
                return AnimationGroup(
                    Wiggle(
                        target,
                        scale_value=1.085,
                        rotation_angle=0.024 * TAU,
                        n_wiggles=3,
                    ),
                    ShowPassingFlash(
                        marker_trace,
                        time_width=0.42,
                    ),
                    lag_ratio=0.0,
                )
            return Wiggle(
                target,
                scale_value=1.075 if tcp_profile else 1.055,
                rotation_angle=(0.022 if tcp_profile else 0.015) * TAU,
                n_wiggles=3 if tcp_profile else 2,
            )
        if STYLE == "warm_papyrus":
            return ApplyMethod(
                target.shift,
                RIGHT * 0.30,
                rate_func=there_and_back,
            )
        if STYLE == "future_minimal":
            return Succession(
                ApplyMethod(
                    target.scale,
                    1.085,
                    rate_func=there_and_back,
                ),
                ApplyMethod(
                    target.shift,
                    RIGHT * 0.14,
                    rate_func=there_and_back,
                ),
            )
        return ApplyMethod(
            target.shift,
            UP * 0.12,
            rate_func=there_and_back,
        )

    return AnimationGroup(
        *[
            style_native_emphasis(target)
            for target, _color in targets[:3]
        ],
        lag_ratio=0.08,
    )


def transition_vector():
    if STYLE == "hand_drawn":
        return LEFT * 0.08 + DOWN * 0.04
    if STYLE == "whiteboard":
        return DOWN * 0.08
    if STYLE == "warm_papyrus":
        return RIGHT * 0.08
    if STYLE == "future_minimal":
        return UP * 0.08
    return LEFT * 0.12


def clean_swap(old, new, shift=None):
    drift = transition_vector() if shift is None else shift
    return Succession(
        FadeOut(old, shift=drift),
        FadeIn(new, shift=-drift),
    )


def caption_swap(old, new):
    if STORY.get("text_transition_mode") != "persistent_lesson_header_handwritten_captions":
        return clean_swap(old, new, shift=DOWN * 0.04)
    if STYLE in {"hand_drawn", "whiteboard"}:
        return Succession(
            Unwrite(old),
            Write(new),
        )
    if STYLE == "warm_papyrus":
        return AnimationGroup(
            FadeOut(old, shift=LEFT * 0.08),
            FadeIn(new, shift=RIGHT * 0.08),
            lag_ratio=0.22,
        )
    if STYLE == "future_minimal":
        return AnimationGroup(
            FadeOut(old, shift=UP * 0.04, scale=0.985),
            FadeIn(new, shift=UP * 0.04, scale=1.015),
            lag_ratio=0.12,
        )
    return AnimationGroup(
        FadeOut(old, shift=LEFT * 0.06),
        FadeIn(new, shift=LEFT * 0.06),
        lag_ratio=0.18,
    )


def caption_swap_duration(cue_duration):
    if STYLE in {"hand_drawn", "whiteboard"}:
        preferred = min(0.38, max(0.24, cue_duration * 0.22))
    elif STYLE == "warm_papyrus":
        preferred = min(0.34, max(0.22, cue_duration * 0.20))
    else:
        preferred = min(0.26, max(0.16, cue_duration * 0.16))
    return min(preferred, max(0.10, cue_duration * 0.65))


def semantic_parts(visual):
    parts = {}
    for part in visual.submobjects:
        key = getattr(part, "semantic_id", None)
        if key:
            parts[key] = part
    return parts


def handshake_transit_token(point, label, color, seed):
    return VGroup(
        mechanism_ellipse(
            point,
            0.82,
            0.34,
            color=color,
            stroke_width=4,
            seed=seed,
            opacity=0.96,
        ),
        fit_text(
            label,
            max_width=0.58,
            size=12,
            color=color,
            weight=BOLD,
        ).move_to(point),
    )


def play_handshake_transit(scene, stage, cycle_index, run_time):
    if stage == 0:
        transits = [([-1.72, 0.82, 0], [1.72, 0.82, 0], "HELLO", P["a"])]
    elif stage == 1:
        transits = [
            ([-2.35, 1.12, 0], [-2.72, 0.3, 0], "DERIVE", P["c"]),
            ([2.35, 1.12, 0], [2.25, 0.3, 0], "DERIVE", P["c"]),
        ]
    elif stage == 2:
        transits = [([1.72, 1.43, 0], [-1.72, 1.43, 0], "ENC", P["b"])]
    elif stage == 3:
        if cycle_index % 2:
            transits = [([1.82, -3.0, 0], [-1.82, -3.0, 0], "FIN", P["b"])]
        else:
            transits = [([-1.82, -2.63, 0], [1.82, -2.63, 0], "FIN", P["a"])]
    else:
        transits = [([-1.72, 1.42, 0], [-0.62, 1.42, 0], "DATA", P["c"])]
    tokens = [
        handshake_transit_token(start, label, color, 820 + stage * 10 + index)
        for index, (start, _end, label, color) in enumerate(transits)
    ]
    paths = [Line(start, end) for start, end, _label, _color in transits]
    scene.add(*tokens)
    scene.play(
        AnimationGroup(
            *[
                MoveAlongPath(token, path)
                for token, path in zip(tokens, paths)
            ],
            lag_ratio=0.0,
        ),
        run_time=run_time,
        rate_func=linear,
    )
    scene.remove(*tokens)


def play_process_motion(scene, visual, stage, cycle_index, run_time):
    parts = semantic_parts(visual)
    carrier = parts.get("process_carrier")
    positions = process_positions()
    stage = min(max(0, stage), len(positions) - 1)
    if stage == 0:
        if carrier is not None:
            whiteboard_tcp = (
                STYLE == "whiteboard"
                and STORY.get("source_visual_profile")
                == "tcp_congestion_control_v1"
            )
            scene.play(
                Wiggle(
                    carrier,
                    scale_value=1.08 if whiteboard_tcp else 1.055,
                    rotation_angle=(0.022 if whiteboard_tcp else 0.012) * TAU,
                    n_wiggles=3 if whiteboard_tcp else 2,
                ),
                run_time=run_time,
            )
        else:
            scene.wait(run_time)
        return
    start = positions[stage - 1]
    end = positions[stage]
    color = story_color(stage)
    whiteboard_tcp = (
        STYLE == "whiteboard"
        and STORY.get("source_visual_profile")
        == "tcp_congestion_control_v1"
    )
    heat_pump_profile = (
        STORY.get("source_visual_profile")
        == "heat_pump_cycle_v1"
    )
    process_token_core = (
        tcp_packet_icon(
            start,
            color,
            size=0.25 if whiteboard_tcp else 0.18,
        )
        if STORY.get("source_visual_profile")
        == "tcp_congestion_control_v1"
        else heat_pump_refrigerant_token(
            start,
            color,
            910 + stage * 10 + cycle_index,
        )
        if heat_pump_profile
        else mechanism_dot(start, color=color, radius=0.075)
    )
    process_token = VGroup(
        process_token_core,
        Circle(
            radius=(
                0.24
                if heat_pump_profile
                else 0.20
                if whiteboard_tcp
                else 0.14
            ),
            stroke_color=color,
            stroke_width=3 if whiteboard_tcp or heat_pump_profile else 2,
            stroke_opacity=(
                0.58
                if heat_pump_profile
                else 0.54
                if whiteboard_tcp
                else 0.34
            ),
        ).move_to(start),
    )
    path = process_travel_path(stage)
    scene.add(process_token)
    animations = [MoveAlongPath(process_token, path)]
    link = parts.get(f"process_link_{stage}")
    if link is not None:
        animations.append(
            ShowPassingFlash(
                link.copy().set_stroke(
                    color=color,
                    width=9 if whiteboard_tcp or heat_pump_profile else 6,
                    opacity=(
                        0.90
                        if whiteboard_tcp or heat_pump_profile
                        else 0.72
                    ),
                ),
                time_width=0.34,
            )
        )
    if carrier is not None:
        animations.append(
            ApplyMethod(
                carrier.scale,
                1.045,
                rate_func=there_and_back,
            )
        )
    scene.play(
        AnimationGroup(*animations, lag_ratio=0.0),
        run_time=run_time,
        rate_func=linear,
    )
    scene.remove(process_token)


def process_recap_animation(visual, run_time):
    parts = semantic_parts(visual)
    positions = process_positions()
    route = VMobject()
    route.set_points_smoothly(process_recap_points())
    tcp_profile = (
        STORY.get("source_visual_profile")
        == "tcp_congestion_control_v1"
    )
    heat_pump_profile = (
        STORY.get("source_visual_profile")
        == "heat_pump_cycle_v1"
    )
    recap_core = (
        tcp_packet_icon(positions[0], P["c"], size=0.20)
        if tcp_profile
        else heat_pump_refrigerant_token(
            positions[0],
            P["c"],
            966,
        )
        if heat_pump_profile
        else mechanism_dot(positions[0], color=P["c"], radius=0.09)
    )
    recap_parts = [
        recap_core,
        Circle(
            radius=0.18,
            stroke_color=P["c"],
            stroke_width=2,
            stroke_opacity=0.42,
        ).move_to(positions[0])
    ]
    if tcp_profile:
        recap_parts.append(
            tiny_label(
                "ACK",
                positions[0] + np.array([0, -0.26, 0]),
                color=P["c"],
                size=9,
            )
        )
    recap_token = VGroup(*recap_parts)
    animations = [MoveAlongPath(recap_token, route)]
    backbone = parts.get("process_backbone")
    if backbone is not None and backbone.submobjects:
        animations.append(
            ShowPassingFlash(
                backbone.submobjects[0].copy().set_stroke(
                    color=P["c"],
                    width=6,
                    opacity=0.82,
                ),
                time_width=0.22,
            )
        )
    feedback = parts.get("process_feedback_return")
    if (
        STORY.get("topology_mode") in {"feedback_loop", "cycle_loop"}
        and feedback is not None
        and feedback.submobjects
    ):
        animations.append(
            Succession(
                Wait(run_time * 0.58),
                ShowPassingFlash(
                    feedback.submobjects[0].copy().set_stroke(
                        color=P["b"],
                        width=7,
                        opacity=0.92,
                    ),
                    time_width=0.28,
                ),
            )
        )
    payoff = parts.get("causal_payoff")
    if payoff is not None:
        if STYLE in {"hand_drawn", "whiteboard"}:
            payoff_animation = Wiggle(
                payoff,
                scale_value=1.055,
                rotation_angle=0.014 * TAU,
                n_wiggles=2,
            )
        elif STYLE == "warm_papyrus":
            payoff_animation = ApplyMethod(
                payoff.shift,
                RIGHT * 0.22,
                rate_func=there_and_back,
            )
        else:
            payoff_animation = ApplyMethod(
                payoff.scale,
                1.045,
                rate_func=there_and_back,
            )
        animations.append(
            Succession(
                Wait(run_time * 0.62),
                payoff_animation,
            )
        )
    recap_animation = AnimationGroup(
        *animations,
        lag_ratio=0.0,
        rate_func=smooth,
    )
    recap_animation.set_run_time(run_time)
    return recap_token, recap_animation


def play_process_recap(scene, visual, run_time):
    recap_token, recap_animation = process_recap_animation(
        visual,
        run_time,
    )
    scene.add(recap_token)
    scene.play(recap_animation)
    scene.remove(recap_token)


def play_argument_motion(scene, visual, stage, cycle_index, run_time):
    parts = semantic_parts(visual)
    key = (
        "framing",
        "shared_benefits",
        "irreversibility",
        "attacker_defender",
        "policy_response",
    )[min(max(0, stage), 4)]
    target = parts.get(key) or parts.get("open_weights_core")
    if target is None:
        scene.wait(run_time)
        return
    if STYLE == "whiteboard":
        trace_index = (
            1
            if key in {"framing", "policy_response"}
            and len(target.submobjects) > 1
            else 0
        )
        trace = (
            target.submobjects[trace_index]
            .copy()
            .set_stroke(
                color=(P["a"], P["c"], P["b"])[stage % 3],
                width=9,
                opacity=0.9,
            )
        )
        scene.play(
            AnimationGroup(
                ShowPassingFlash(trace, time_width=0.46),
                Wiggle(
                    target,
                    scale_value=1.045,
                    rotation_angle=0.014 * TAU,
                    n_wiggles=2,
                ),
                lag_ratio=0.0,
            ),
            run_time=run_time,
        )
        return
    if STYLE == "warm_papyrus":
        scene.play(
            Rotate(
                target,
                angle=(0.026 if cycle_index % 2 == 0 else -0.026),
                rate_func=there_and_back,
            ),
            run_time=run_time,
        )
        return
    if STYLE == "future_minimal":
        scene.play(
            Succession(
                ApplyMethod(
                    target.scale,
                    1.055,
                    rate_func=there_and_back,
                ),
                ApplyMethod(
                    target.shift,
                    RIGHT * (0.08 if cycle_index % 2 == 0 else -0.08),
                    rate_func=there_and_back,
                ),
            ),
            run_time=run_time,
        )
        return
    scene.play(
        ApplyMethod(
            target.shift,
            UP * (0.10 if cycle_index % 2 == 0 else -0.10),
            rate_func=there_and_back,
        ),
        run_time=run_time,
    )


def wait_with_story_motion(scene, visual, stage, duration):
    duration = max(0.0, float(duration))
    kind = STORY.get("kind")
    if (
        kind
        not in {
            "mechanism_handshake",
            "causal_explainer",
            "open_weights_debate",
        }
        or duration < 0.9
    ):
        if duration > 0:
            scene.wait(duration)
        return
    cycle_count = max(1, int(duration / 1.5))
    segment_duration = duration / cycle_count
    for cycle_index in range(cycle_count):
        lead = min(0.56, max(0.24, segment_duration * 0.34))
        transit = min(0.62, max(0.4, segment_duration * 0.42))
        tail = max(0.0, segment_duration - lead - transit)
        scene.wait(lead)
        if kind == "mechanism_handshake":
            play_handshake_transit(scene, stage, cycle_index, transit)
        elif kind == "open_weights_debate":
            play_argument_motion(
                scene,
                visual,
                stage,
                cycle_index,
                transit,
            )
        else:
            play_process_motion(scene, visual, stage, cycle_index, transit)
        if tail > 0:
            scene.wait(tail)


def semantic_visual_swap(old, new):
    if STORY.get("transition_mode") != "semantic_continuity":
        return clean_swap(old, new)
    old_parts = semantic_parts(old)
    new_parts = semantic_parts(new)
    if not old_parts or not new_parts:
        return clean_swap(old, new)
    animations = []
    for key, old_part in old_parts.items():
        if key in new_parts:
            animations.append(ReplacementTransform(old_part, new_parts[key]))
        else:
            animations.append(FadeOut(old_part, shift=transition_vector()))
    for key, new_part in new_parts.items():
        if key in old_parts:
            continue
        if STYLE in {"hand_drawn", "whiteboard", "warm_papyrus"}:
            animations.append(Create(new_part))
        else:
            animations.append(FadeIn(new_part, shift=-transition_vector() * 1.5, scale=0.98))
    return AnimationGroup(*animations, lag_ratio=0.06)


def technology_caption(value):
    caption = complete_wrap_text(
        value,
        max_width=7.15,
        max_height=0.96,
        chars=27,
        lines=2,
        size=32,
        color=P["ink"],
        weight=BOLD,
    )
    caption.move_to(DOWN * 5.80)
    return caption


def technology_title_center():
    return complete_wrap_text(
        STORY.get("hook_title", {}).get(
            "text",
            "The adolescence of technology",
        ),
        max_width=7.25,
        max_height=2.15,
        chars=22,
        lines=2,
        size=64,
        color=P["ink"],
        weight=BOLD,
    ).move_to([0, 0.35, 0])


def technology_title_header():
    return complete_wrap_text(
        STORY.get("hook_title", {}).get(
            "text",
            "The adolescence of technology",
        ),
        max_width=7.35,
        max_height=1.16,
        chars=34,
        lines=2,
        size=42,
        color=P["ink"],
        weight=BOLD,
    ).move_to(UP * 5.86)


def technology_caption_swap(old, new):
    if old is None:
        return FadeIn(new)
    return AnimationGroup(
        FadeOut(old),
        FadeIn(new),
        lag_ratio=0.15,
    )


def lecun_wait_until(scene, origin, offset):
    target = origin + max(0.0, float(offset))
    if scene.time < target:
        scene.wait(target - scene.time)


def lecun_cue_start(item, terms, fallback):
    terms = tuple(str(term).lower() for term in terms)
    for cue in item.get("params", {}).get("captions", []):
        text = str(cue.get("text", "")).lower()
        if any(term in text for term in terms):
            return float(cue.get("start_seconds", fallback))
    return float(fallback)


def lecun_text(value, point, size, color="#F8FBFF", width=7.8, weight=BOLD):
    label = Text(
        value,
        font="Avenir Next",
        font_size=size,
        color=color,
        weight=weight,
        line_spacing=0.82,
    )
    if label.width > width:
        label.scale_to_fit_width(width)
    label.move_to(point)
    return label


def lecun_portrait_pin():
    frame = RoundedRectangle(
        width=3.92,
        height=4.55,
        corner_radius=0.22,
        stroke_color="#D8FFF6",
        stroke_width=5,
        fill_color="#07131E",
        fill_opacity=0.94,
    )
    photo = ImageMobject(LECUN_PORTRAIT_PATH)
    photo.set_height(4.30)
    photo.move_to(frame.get_center() + UP * 0.05)
    photo.set_z_index(3)
    frame.set_z_index(2)
    name_plate = RoundedRectangle(
        width=3.48,
        height=0.70,
        corner_radius=0.18,
        fill_color="#07131E",
        fill_opacity=0.94,
        stroke_color="#67E8D4",
        stroke_width=2,
    ).move_to(frame.get_bottom() + UP * 0.46)
    name = lecun_text(
        "YANN LECUN",
        name_plate.get_center(),
        28,
        color="#FFFFFF",
        width=3.05,
    )
    name_plate.set_z_index(4)
    name.set_z_index(5)
    pin = Circle(
        radius=0.13,
        fill_color="#FBBF24",
        fill_opacity=1,
        stroke_color="#FFFFFF",
        stroke_width=2,
    ).move_to(frame.get_top() + UP * 0.08)
    pin.set_z_index(5)
    return Group(frame, photo, name_plate, name, pin)


def lecun_world_station():
    halo = Circle(
        radius=2.05,
        stroke_color="#67E8D4",
        stroke_width=2,
        stroke_opacity=0.40,
        fill_color="#0A2233",
        fill_opacity=0.84,
    )
    ring = Circle(
        radius=1.62,
        stroke_color="#FFFFFF",
        stroke_width=4,
        stroke_opacity=0.92,
    )
    globe = Circle(
        radius=1.30,
        stroke_color="#67E8D4",
        stroke_width=3,
        fill_color="#0E5B75",
        fill_opacity=0.72,
    )
    longitude = Ellipse(
        width=1.05,
        height=2.36,
        stroke_color="#9AF6E7",
        stroke_width=2,
        stroke_opacity=0.68,
    )
    latitude = Ellipse(
        width=2.36,
        height=0.92,
        stroke_color="#9AF6E7",
        stroke_width=2,
        stroke_opacity=0.68,
    )
    nodes = VGroup(
        *[
            Dot(point, radius=0.09, color=color)
            for point, color in (
                ([-0.82, 0.46, 0], "#FBBF24"),
                ([0.72, 0.72, 0], "#FB7185"),
                ([0.62, -0.76, 0], "#67E8D4"),
                ([-0.70, -0.58, 0], "#FFFFFF"),
            )
        ]
    )
    title = lecun_text(
        "WORLD MODEL",
        [0, -1.70, 0],
        31,
        color="#FFFFFF",
        width=3.35,
    )
    return VGroup(halo, ring, globe, longitude, latitude, nodes, title)


def elastic_layer_stack(count=5, width=5.6, inner_width=3.2, top=1.35, gap=0.30, height=0.62):
    bars = VGroup()
    for index in range(count):
        y = top - index * (height + gap)
        outer = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.14,
            stroke_color="#9AF6E7",
            stroke_width=3,
            fill_color="#0A1F30",
            fill_opacity=0.90,
        ).move_to([0, y, 0])
        inner = RoundedRectangle(
            width=inner_width,
            height=height - 0.16,
            corner_radius=0.10,
            stroke_color="#FBBF24",
            stroke_width=2,
            fill_color="#123C4A",
            fill_opacity=0.96,
        ).move_to([-(width - inner_width) / 2 + 0.10, y, 0])
        bars.add(VGroup(outer, inner))
    return bars


def construct_elastic_llm_nesting(scene, items):
    """One nested-model world: the same object is zoomed, sliced, and multiplied."""
    world = VGroup()
    for scale_width, scale_height, opacity in (
        (8.9, 15.7, 0.05),
        (7.3, 12.6, 0.07),
        (5.9, 9.9, 0.09),
    ):
        world.add(
            RoundedRectangle(
                width=scale_width,
                height=scale_height,
                corner_radius=0.55,
                stroke_color="#67E8D4",
                stroke_width=2,
                stroke_opacity=opacity * 3.2,
                fill_color="#06121C",
                fill_opacity=opacity,
            )
        )
    world.set_z_index(-5)
    scene.add(world)

    # Beat 1: the hook stands alone, then the nested pair appears.
    item = items[0]
    origin = scene.time
    duration = float(item["duration_seconds"])
    hook_top = lecun_text("ONE MODEL,", [0, 6.05, 0], 78, color="#FFFFFF", width=8.0)
    hook_bottom = lecun_text("MANY SIZES", [0, 4.95, 0], 78, color="#67E8D4", width=8.0)
    hook_group = VGroup(hook_top, hook_bottom)
    scene.play(
        AnimationGroup(
            FadeIn(hook_top, shift=DOWN * 0.16),
            FadeIn(hook_bottom, shift=DOWN * 0.10),
            lag_ratio=0.22,
        ),
        run_time=min(1.05, max(0.72, duration * 0.22)),
    )
    outer_model = RoundedRectangle(
        width=6.9,
        height=6.9,
        corner_radius=0.42,
        stroke_color="#E9FFF9",
        stroke_width=6,
        fill_color="#0A1F30",
        fill_opacity=0.92,
    ).move_to([0, -0.75, 0])
    outer_tag = lecun_text(
        "GEMMA 3N  ·  E4B",
        [0, 2.05, 0],
        30,
        color="#C9FDF3",
        width=5.6,
    )
    params_tag = lecun_text(
        "8B RAW PARAMS",
        [-2.05, -3.85, 0],
        22,
        color="#8FB3C7",
        width=2.9,
    )
    scene.play(
        AnimationGroup(
            Create(outer_model),
            FadeIn(outer_tag, shift=DOWN * 0.10),
            FadeIn(params_tag),
            lag_ratio=0.14,
        ),
        run_time=min(1.05, max(0.70, duration * 0.22)),
    )
    hiding_start = lecun_cue_start(item, ("hiding", "smaller model"), duration * 0.55)
    lecun_wait_until(scene, origin, min(hiding_start, duration * 0.72))
    inner_model = RoundedRectangle(
        width=3.9,
        height=3.9,
        corner_radius=0.30,
        stroke_color="#FBBF24",
        stroke_width=5,
        fill_color="#123C4A",
        fill_opacity=0.96,
    ).move_to([0, -0.75, 0])
    inner_tag = lecun_text("E2B", [0, -0.75, 0], 56, color="#FFFFFF", width=2.6)
    inner_pulse = inner_model.copy().set_fill(opacity=0).set_stroke(
        "#FBBF24", width=9, opacity=0.85
    )
    scene.play(
        AnimationGroup(
            FadeIn(inner_model, scale=0.76),
            FadeIn(inner_tag, scale=0.82),
            FadeIn(inner_pulse, scale=0.70),
            lag_ratio=0.10,
        ),
        run_time=min(0.95, max(0.60, duration * 0.18)),
    )
    scene.play(
        FadeOut(inner_pulse, scale=1.28),
        run_time=min(0.45, max(0.28, duration * 0.08)),
    )
    lecun_wait_until(scene, origin, duration)

    # Beat 2: zoom into the layers; nested training happens simultaneously.
    item = items[1]
    origin = scene.time
    duration = float(item["duration_seconds"])
    scene.play(
        AnimationGroup(
            hook_group.animate.scale(0.42).move_to([-2.35, 7.05, 0]),
            FadeOut(params_tag),
            lag_ratio=0.08,
        ),
        run_time=min(0.85, max(0.55, duration * 0.09)),
    )
    matformer_label = lecun_text("MATFORMER", [0, 3.30, 0], 42, color="#67E8D4", width=6.2)
    matryoshka_label = lecun_text(
        "MATRYOSHKA TRANSFORMER",
        [0, 2.62, 0],
        23,
        color="#C9FDF3",
        width=5.8,
    )
    layers = elastic_layer_stack()
    scene.play(
        AnimationGroup(
            Transform(
                outer_model,
                outer_model.copy().stretch_to_fit_height(7.0).move_to([0, -1.55, 0]),
            ),
            FadeOut(inner_model),
            FadeOut(inner_tag),
            outer_tag.animate.move_to([0, 4.15, 0]).scale(0.78),
            FadeIn(matformer_label, shift=DOWN * 0.14),
            FadeIn(matryoshka_label, shift=DOWN * 0.10),
            lag_ratio=0.07,
        ),
        run_time=min(1.20, max(0.85, duration * 0.14)),
    )
    stack_start = lecun_cue_start(item, ("trains", "e four"), duration * 0.38)
    lecun_wait_until(scene, origin, min(stack_start, duration * 0.48))
    scene.play(
        LaggedStart(
            *[FadeIn(layer[0], shift=RIGHT * 0.18) for layer in layers],
            lag_ratio=0.12,
        ),
        run_time=min(1.30, max(0.90, duration * 0.13)),
    )
    inner_start = lecun_cue_start(item, ("fully working", "e two"), duration * 0.62)
    lecun_wait_until(scene, origin, min(inner_start, duration * 0.72))
    scene.play(
        LaggedStart(
            *[FadeIn(layer[1], shift=RIGHT * 0.12) for layer in layers],
            lag_ratio=0.12,
        ),
        run_time=min(1.10, max(0.75, duration * 0.11)),
    )
    same_time_start = lecun_cue_start(item, ("same time", "optimized"), duration * 0.82)
    lecun_wait_until(scene, origin, min(same_time_start, duration * 0.90))
    trained_label = lecun_text(
        "TRAINED TOGETHER",
        [0, -4.35, 0],
        27,
        color="#FBBF24",
        width=4.6,
    )
    scene.play(
        AnimationGroup(
            FadeIn(trained_label, shift=UP * 0.12),
            *[
                layer[1].animate.set_stroke("#FBBF24", width=4, opacity=1.0)
                for layer in layers
            ],
            lag_ratio=0.05,
        ),
        run_time=min(0.95, max(0.62, duration * 0.10)),
    )
    lecun_wait_until(scene, origin, duration)

    # Beat 3: Mix-n-Match slices custom sizes along the E2B-E4B spectrum.
    item = items[2]
    origin = scene.time
    duration = float(item["duration_seconds"])
    mix_label = lecun_text("MIX-N-MATCH", [0, 3.30, 0], 42, color="#FFFFFF", width=6.2)
    scene.play(
        AnimationGroup(
            FadeOut(matformer_label, shift=UP * 0.10),
            FadeOut(matryoshka_label, shift=UP * 0.10),
            FadeOut(trained_label),
            FadeIn(mix_label, shift=DOWN * 0.12),
            outer_model.animate.shift(LEFT * 0.55),
            layers.animate.shift(LEFT * 0.55),
            outer_tag.animate.shift(LEFT * 0.55),
            lag_ratio=0.05,
        ),
        run_time=min(0.95, max(0.65, duration * 0.11)),
    )
    slider = Line([3.62, -4.05, 0], [3.62, 1.45, 0], color="#E9FFF9", stroke_width=4)
    slider_bottom = lecun_text("E2B · 2GB", [3.62, -4.62, 0], 22, color="#C9FDF3", width=1.9)
    slider_top = lecun_text("E4B · 3GB", [3.62, 1.98, 0], 22, color="#C9FDF3", width=1.9)
    slider_marker = Dot([3.62, -4.05, 0], radius=0.15, color="#FBBF24")
    slider_marker.set_stroke("#FFFFFF", width=3)
    between_start = lecun_cue_start(item, ("between", "size"), duration * 0.16)
    lecun_wait_until(scene, origin, min(between_start, duration * 0.30))
    scene.play(
        AnimationGroup(
            Create(slider),
            FadeIn(slider_bottom),
            FadeIn(slider_top),
            FadeIn(slider_marker, scale=0.7),
            lag_ratio=0.10,
        ),
        run_time=min(0.85, max(0.55, duration * 0.11)),
    )
    scene.play(
        slider_marker.animate.move_to([3.62, -1.15, 0]),
        run_time=min(0.75, max(0.50, duration * 0.10)),
        rate_func=smooth,
    )
    resize_start = lecun_cue_start(item, ("resizing", "slices"), duration * 0.48)
    lecun_wait_until(scene, origin, min(resize_start, duration * 0.60))
    new_widths = (2.4, 3.6, 1.9, 3.1, 2.7)
    resize_animations = []
    for layer, width in zip(layers, new_widths):
        inner = layer[1]
        target = inner.copy().stretch_to_fit_width(width)
        target.move_to(
            [
                inner.get_left()[0] + width / 2,
                inner.get_center()[1],
                0,
            ]
        )
        resize_animations.append(Transform(inner, target))
    scene.play(
        AnimationGroup(*resize_animations, lag_ratio=0.09),
        run_time=min(1.05, max(0.70, duration * 0.13)),
    )
    skip_start = lecun_cue_start(item, ("skipping",), duration * 0.68)
    lecun_wait_until(scene, origin, min(skip_start, duration * 0.78))
    scene.play(
        layers[3].animate.set_opacity(0.22),
        run_time=min(0.55, max(0.35, duration * 0.08)),
    )
    retrain_start = lecun_cue_start(item, ("no retraining", "retraining"), duration * 0.82)
    lecun_wait_until(scene, origin, min(retrain_start, duration * 0.88))
    no_retrain = lecun_text("NO RETRAINING", [0, -4.35, 0], 30, color="#FBBF24", width=4.7)
    scene.play(FadeIn(no_retrain, scale=0.86), run_time=min(0.6, max(0.35, duration * 0.08)))
    lecun_wait_until(scene, origin, duration)

    # Beat 4: pull back; one training run becomes a family of deployed sizes.
    item = items[3]
    origin = scene.time
    duration = float(item["duration_seconds"])
    diagram = VGroup(outer_model, layers)
    scene.play(
        AnimationGroup(
            FadeOut(no_retrain),
            FadeOut(slider),
            FadeOut(slider_bottom),
            FadeOut(slider_top),
            FadeOut(slider_marker),
            FadeOut(mix_label, shift=UP * 0.10),
            FadeOut(outer_tag, shift=UP * 0.10),
            diagram.animate.scale(0.58).move_to([-2.05, 1.55, 0]),
            lag_ratio=0.05,
        ),
        run_time=min(1.05, max(0.72, duration * 0.09)),
    )
    flextron_start = lecun_cue_start(item, ("flextron", "nvidia"), duration * 0.06)
    lecun_wait_until(scene, origin, min(flextron_start, duration * 0.22))
    flextron_plate = RoundedRectangle(
        width=5.9,
        height=1.30,
        corner_radius=0.22,
        stroke_color="#9AF6E7",
        stroke_width=3,
        fill_color="#0A1F30",
        fill_opacity=0.94,
    ).move_to([0, 4.35, 0])
    flextron_title = lecun_text(
        "NVIDIA FLEXTRON",
        [0, 4.62, 0],
        27,
        color="#FFFFFF",
        width=5.3,
    )
    flextron_detail = lecun_text(
        "7.63% OF TRAINING TOKENS",
        [0, 4.06, 0],
        22,
        color="#FBBF24",
        width=5.3,
    )
    scene.play(
        AnimationGroup(
            FadeIn(flextron_plate, scale=0.92),
            FadeIn(flextron_title),
            FadeIn(flextron_detail),
            lag_ratio=0.10,
        ),
        run_time=min(0.85, max(0.55, duration * 0.08)),
    )
    family_start = lecun_cue_start(item, ("family", "train once"), duration * 0.38)
    lecun_wait_until(scene, origin, min(family_start, duration * 0.52))
    device_specs = (
        (2.55, 1.65, "SERVER", [2.55, 2.55, 0]),
        (1.85, 1.20, "LAPTOP", [2.55, 0.35, 0]),
        (1.15, 0.78, "PHONE", [2.55, -1.55, 0]),
    )
    blocks = VGroup()
    tags = VGroup()
    seeds = []
    spawn_animations = []
    for width, height, name, point in device_specs:
        block = RoundedRectangle(
            width=width,
            height=height,
            corner_radius=0.18,
            stroke_color="#E9FFF9",
            stroke_width=4,
            fill_color="#123C4A",
            fill_opacity=0.94,
        ).move_to(point)
        tag = lecun_text(name, [point[0], point[1] - height / 2 - 0.34, 0], 20, color="#C9FDF3", width=width + 0.3)
        blocks.add(block)
        tags.add(tag)
        seed = outer_model.copy().set_fill(opacity=0.3)
        seeds.append(seed)
        spawn_animations.append(Transform(seed, block))
    scene.play(
        LaggedStart(*spawn_animations, lag_ratio=0.16),
        run_time=min(1.30, max(0.85, duration * 0.13)),
    )
    scene.remove(*seeds)
    scene.add(blocks)
    scene.play(
        LaggedStart(*[FadeIn(tag, shift=UP * 0.08) for tag in tags], lag_ratio=0.12),
        run_time=min(0.60, max(0.40, duration * 0.06)),
    )
    takeaway_start = lecun_cue_start(item, ("train once", "whole family"), duration * 0.55)
    lecun_wait_until(scene, origin, min(takeaway_start, duration * 0.66))
    takeaway_top = lecun_text("TRAIN ONCE.", [0, -3.05, 0], 56, color="#FFFFFF", width=7.6)
    takeaway_bottom = lecun_text(
        "RESIZE ANYWHERE.",
        [0, -4.15, 0],
        56,
        color="#67E8D4",
        width=7.6,
    )
    scene.play(
        AnimationGroup(
            FadeIn(takeaway_top, shift=UP * 0.14),
            FadeIn(takeaway_bottom, shift=UP * 0.10),
            lag_ratio=0.18,
        ),
        run_time=min(1.00, max(0.68, duration * 0.10)),
    )
    prove_start = lecun_cue_start(item, ("prove", "from scratch"), duration * 0.80)
    lecun_wait_until(scene, origin, min(prove_start, duration * 0.88))
    caveat = lecun_text(
        "sliced models still must prove parity",
        [0, -5.05, 0],
        22,
        color="#8FB3C7",
        width=6.6,
    )
    scene.play(FadeIn(caveat, shift=UP * 0.08), run_time=min(0.6, max(0.36, duration * 0.07)))
    lecun_wait_until(scene, origin, duration)


def construct_lecun_world_model_bet(scene, items):
    """One full-frame world, one guided route, and only narration-tied motion."""
    earth = ImageMobject(EARTH_IMAGE_PATH)
    earth.set_height(18.4)
    earth.shift(RIGHT * 1.25 + DOWN * 0.18)
    earth.set_opacity(0.96)
    earth.set_z_index(-5)
    grade = Rectangle(
        width=9.2,
        height=16.25,
        fill_color="#03111D",
        fill_opacity=0.52,
        stroke_opacity=0,
    )
    grade.set_z_index(-4)
    vignette_top = Rectangle(
        width=9.2,
        height=4.6,
        fill_color="#02070D",
        fill_opacity=0.38,
        stroke_opacity=0,
    ).move_to(UP * 5.75)
    vignette_top.set_z_index(-3)
    scene.add(earth, grade, vignette_top)

    route_points = (
        ([-3.58, 6.15, 0], [-4.0, 4.1, 0], [-1.5, 2.4, 0], [0.05, 0.25, 0]),
        ([0.05, 0.25, 0], [2.2, -0.3, 0], [3.75, -1.2, 0], [2.3, -3.2, 0]),
        ([2.3, -3.2, 0], [0.8, -5.15, 0], [-2.65, -4.9, 0], [-2.2, -6.35, 0]),
    )
    paths = [
        CubicBezier(*[np.array(point, dtype=float) for point in values])
        for values in route_points
    ]
    route_map = VGroup(
        *[
            DashedVMobject(
                path.copy(),
                num_dashes=24,
                dashed_ratio=0.56,
            ).set_stroke("#E9FFF9", width=4, opacity=0.26)
            for path in paths
        ]
    )
    scene.add(route_map)
    marker = Dot(
        route_points[0][0],
        radius=0.14,
        color="#FBBF24",
    )
    marker.add_updater(
        lambda mob: mob.set_stroke("#FFFFFF", width=3, opacity=0.92)
    )
    marker.set_z_index(10)

    # Beat 1: the financing is the hook, with the portrait pinned to the claim.
    item = items[0]
    origin = scene.time
    end = origin + float(item["duration_seconds"])
    kicker = lecun_text(
        "YANN LECUN'S BET",
        [0, 6.22, 0],
        34,
        color="#C9FDF3",
        width=7.4,
    )
    amount = lecun_text(
        "$1.03B",
        [0, 4.82, 0],
        90,
        color="#FFFFFF",
        width=7.5,
    )
    underline = Line(
        [-2.68, 4.10, 0],
        [2.68, 4.10, 0],
        color="#FBBF24",
        stroke_width=7,
    )
    bet_label = lecun_text(
        "AGAINST AN LLM-ONLY FUTURE",
        [0, 3.62, 0],
        25,
        color="#FBBF24",
        width=7.4,
    )
    portrait = lecun_portrait_pin().move_to([0, 0.75, 0])
    ami = lecun_text(
        "AMI LABS  •  2026",
        [0, -2.05, 0],
        25,
        color="#C9FDF3",
        width=5.8,
    )
    funding_group = Group(kicker, amount, underline, bet_label, portrait, ami)
    scene.play(
        AnimationGroup(
            FadeIn(kicker, shift=DOWN * 0.14),
            FadeIn(amount, scale=0.92),
            Create(underline),
            lag_ratio=0.16,
        ),
        run_time=min(1.15, max(0.82, float(item["duration_seconds"]) * 0.23)),
    )
    scene.play(
        AnimationGroup(
            FadeIn(bet_label, shift=UP * 0.12),
            FadeIn(portrait, shift=UP * 0.18),
            FadeIn(ami),
            lag_ratio=0.12,
        ),
        run_time=min(0.92, max(0.62, float(item["duration_seconds"]) * 0.18)),
    )
    scene.add(marker)
    scene.play(
        Create(paths[0].copy().set_stroke("#E9FFF9", width=5, opacity=0.92)),
        MoveAlongPath(marker, paths[0]),
        run_time=min(0.88, max(0.60, float(item["duration_seconds"]) * 0.16)),
        rate_func=smooth,
    )
    lecun_wait_until(scene, origin, float(item["duration_seconds"]))

    # Beat 2: the same route arrives at the proposed world-model program.
    item = items[1]
    origin = scene.time
    end = origin + float(item["duration_seconds"])
    station = lecun_world_station().move_to([0, -0.05, 0])
    compact_funding = Group(kicker, amount, underline, bet_label, portrait, ami)
    scene.play(
        AnimationGroup(
            compact_funding.animate.scale(0.46).move_to([-2.18, 4.63, 0]),
            earth.animate.scale(1.06).shift(LEFT * 0.60 + UP * 0.18),
            FadeIn(station, scale=0.76),
            lag_ratio=0.05,
        ),
        run_time=min(1.15, max(0.82, float(item["duration_seconds"]) * 0.28)),
    )
    station_pulse = station[1].copy().set_stroke(
        "#67E8D4",
        width=8,
        opacity=0.80,
    )
    scene.play(
        AnimationGroup(
            Create(paths[1].copy().set_stroke("#E9FFF9", width=5, opacity=0.92)),
            MoveAlongPath(marker, paths[1]),
            FadeIn(station_pulse, scale=0.72),
            lag_ratio=0.02,
        ),
        run_time=min(0.92, max(0.62, float(item["duration_seconds"]) * 0.20)),
        rate_func=smooth,
    )
    scene.play(
        FadeOut(station_pulse, scale=1.38),
        run_time=min(0.42, max(0.28, float(item["duration_seconds"]) * 0.09)),
    )
    lecun_wait_until(scene, origin, float(item["duration_seconds"]))

    # Beat 3: follow the same marker from token prediction into physical prediction.
    item = items[2]
    origin = scene.time
    duration = float(item["duration_seconds"])
    station_target = station.copy().scale(0.48).move_to([2.55, 4.65, 0])
    scene.play(
        Transform(station, station_target),
        earth.animate.scale(1.035).shift(RIGHT * 0.34 + DOWN * 0.24),
        run_time=min(0.70, max(0.48, duration * 0.08)),
    )
    next_word_label = lecun_text(
        "NEXT WORD",
        [0, 2.72, 0],
        29,
        color="#C9FDF3",
        width=4.6,
    )
    tokens = VGroup()
    for index, value in enumerate(("THE", "NEXT", "WORD")):
        token = lecun_text(
            value,
            [-2.68 + index * 2.68, 1.65, 0],
            39,
            color="#FFFFFF",
            width=2.05,
        )
        ring = RoundedRectangle(
            width=2.10,
            height=1.12,
            corner_radius=0.32,
            stroke_color="#9AF6E7",
            stroke_width=3,
            fill_color="#071A29",
            fill_opacity=0.84,
        ).move_to(token)
        tokens.add(VGroup(ring, token))
    token_arrows = VGroup(
        Arrow(
            tokens[0].get_right(),
            tokens[1].get_left(),
            buff=0.16,
            color="#FBBF24",
            stroke_width=5,
        ),
        Arrow(
            tokens[1].get_right(),
            tokens[2].get_left(),
            buff=0.16,
            color="#FBBF24",
            stroke_width=5,
        ),
    )
    token_group = VGroup(next_word_label, tokens, token_arrows)
    scene.play(
        FadeIn(next_word_label, shift=DOWN * 0.12),
        LaggedStart(
            *[FadeIn(token, scale=0.86) for token in tokens],
            lag_ratio=0.18,
        ),
        run_time=min(0.92, max(0.64, duration * 0.11)),
    )
    scene.play(
        LaggedStart(
            Create(token_arrows[0]),
            tokens[0][1].animate.set_color("#FBBF24"),
            Create(token_arrows[1]),
            tokens[1][1].animate.set_color("#FBBF24"),
            tokens[2][1].animate.set_color("#FBBF24"),
            lag_ratio=0.14,
        ),
        run_time=min(1.14, max(0.80, duration * 0.13)),
    )

    physical_start = lecun_cue_start(
        item,
        ("lecun wants", "what happens"),
        duration * 0.38,
    )
    lecun_wait_until(scene, origin, physical_start)
    next_state_label = lecun_text(
        "NEXT STATE",
        [0, 2.72, 0],
        29,
        color="#FBBF24",
        width=4.6,
    )
    floor = Line(
        [-3.55, -3.92, 0],
        [3.55, -3.92, 0],
        color="#FFFFFF",
        stroke_width=5,
        stroke_opacity=0.88,
    )
    ball = Circle(
        radius=0.30,
        fill_color="#FBBF24",
        fill_opacity=1,
        stroke_color="#FFFFFF",
        stroke_width=3,
    ).move_to([-2.75, -2.05, 0])
    prediction_path = ArcBetweenPoints(
        ball.get_center(),
        [2.65, -3.55, 0],
        angle=-0.58,
    )
    prediction_path.set_stroke(
        "#FFFFFF",
        width=4,
        opacity=0.80,
    )
    dashed_prediction = DashedVMobject(
        prediction_path.copy(),
        num_dashes=22,
        dashed_ratio=0.55,
    ).set_stroke("#FFFFFF", width=4, opacity=0.72)
    ghost_ball = ball.copy().set_fill("#FBBF24", opacity=0.24)
    ghost_ball.set_stroke("#FFFFFF", width=2, opacity=0.30)
    ghost_ball.move_to(prediction_path.get_end())
    sensor = AnnularSector(
        inner_radius=0.06,
        outer_radius=2.05,
        angle=0.72,
        start_angle=-0.36,
        fill_color="#67E8D4",
        fill_opacity=0.16,
        stroke_color="#67E8D4",
        stroke_width=2,
        stroke_opacity=0.50,
    ).move_arc_center_to([-3.75, -2.95, 0])
    sensor_eye = Dot([-3.75, -2.95, 0], radius=0.16, color="#67E8D4")
    physical = VGroup(
        next_state_label,
        floor,
        ball,
        dashed_prediction,
        ghost_ball,
        sensor,
        sensor_eye,
    )
    scene.play(
        AnimationGroup(
            FadeOut(token_group, shift=UP * 0.16),
            FadeIn(next_state_label, shift=DOWN * 0.16),
            Create(floor),
            FadeIn(sensor),
            FadeIn(sensor_eye),
            FadeIn(ball, scale=0.72),
            lag_ratio=0.06,
        ),
        run_time=min(0.86, max(0.60, duration * 0.10)),
    )
    scene.play(
        AnimationGroup(
            Create(dashed_prediction),
            FadeIn(ghost_ball, scale=0.60),
            lag_ratio=0.12,
        ),
        run_time=min(0.75, max(0.50, duration * 0.09)),
    )
    scene.play(
        MoveAlongPath(ball, prediction_path),
        run_time=min(1.00, max(0.70, duration * 0.12)),
        rate_func=smooth,
    )

    modalities_start = lecun_cue_start(
        item,
        ("video", "sensors", "actions"),
        duration * 0.70,
    )
    lecun_wait_until(scene, origin, modalities_start)
    modality_values = (
        ("VIDEO", "#67E8D4"),
        ("SENSORS", "#FFFFFF"),
        ("ACTIONS", "#FB7185"),
    )
    modalities = VGroup()
    for index, (value, color) in enumerate(modality_values):
        center = [-2.65 + index * 2.65, -5.15, 0]
        dot = Circle(
            radius=0.24,
            fill_color=color,
            fill_opacity=1,
            stroke_color="#FFFFFF",
            stroke_width=2,
        ).move_to([center[0], center[1] + 0.50, 0])
        label = lecun_text(
            value,
            center,
            23,
            color=color,
            width=2.0,
        )
        modalities.add(VGroup(dot, label))
    scene.play(
        LaggedStart(
            *[FadeIn(group, scale=0.72) for group in modalities],
            lag_ratio=0.22,
        ),
        run_time=min(0.94, max(0.64, duration * 0.11)),
    )
    scene.play(
        Create(paths[2].copy().set_stroke("#E9FFF9", width=5, opacity=0.92)),
        MoveAlongPath(marker, paths[2]),
        run_time=min(0.82, max(0.56, duration * 0.09)),
        rate_func=smooth,
    )
    lecun_wait_until(scene, origin, duration)

    # Beat 4: pull back to the completed argument; the last change is the challenge.
    item = items[3]
    origin = scene.time
    duration = float(item["duration_seconds"])
    payoff = lecun_text(
        "REAL INTELLIGENCE",
        [0, 2.65, 0],
        45,
        color="#FFFFFF",
        width=7.65,
    )
    world = lecun_text(
        "STARTS IN\nTHE WORLD",
        [0, 0.28, 0],
        77,
        color="#FBBF24",
        width=7.55,
    )
    not_language = lecun_text(
        "not only in language",
        [0, -1.72, 0],
        31,
        color="#C9FDF3",
        width=6.8,
        weight=NORMAL,
    )
    world_ring = Circle(
        radius=3.02,
        stroke_color="#67E8D4",
        stroke_width=4,
        stroke_opacity=0.72,
    ).move_to([0, 0.35, 0])
    world_ring_2 = Circle(
        radius=3.40,
        stroke_color="#FFFFFF",
        stroke_width=2,
        stroke_opacity=0.30,
    ).move_to([0, 0.35, 0])
    final_group = VGroup(
        payoff,
        world,
        not_language,
        world_ring,
        world_ring_2,
    )
    scene.play(
        AnimationGroup(
            FadeOut(physical),
            FadeOut(modalities),
            station.animate.scale(0.82).move_to([2.88, 5.42, 0]),
            compact_funding.animate.scale(0.80).move_to([-2.82, 5.48, 0]),
            earth.animate.scale(1.12).shift(LEFT * 0.45 + UP * 0.18),
            FadeIn(world_ring, scale=0.78),
            FadeIn(world_ring_2, scale=0.70),
            lag_ratio=0.03,
        ),
        run_time=min(1.02, max(0.72, duration * 0.15)),
    )
    scene.play(
        AnimationGroup(
            FadeIn(payoff, shift=DOWN * 0.15),
            FadeIn(world, scale=0.88),
            FadeIn(not_language, shift=UP * 0.15),
            lag_ratio=0.12,
        ),
        run_time=min(1.10, max(0.76, duration * 0.16)),
    )
    prove_start = lecun_cue_start(
        item,
        ("now he", "prove"),
        duration * 0.68,
    )
    lecun_wait_until(scene, origin, prove_start)
    challenge_bar = RoundedRectangle(
        width=5.70,
        height=1.18,
        corner_radius=0.34,
        fill_color="#FBBF24",
        fill_opacity=0.96,
        stroke_color="#FFFFFF",
        stroke_width=2,
    ).move_to([0, -4.62, 0])
    challenge = lecun_text(
        "NOW PROVE IT.",
        challenge_bar.get_center(),
        42,
        color="#07131E",
        width=5.10,
    )
    scene.play(
        AnimationGroup(
            FadeIn(challenge_bar, shift=UP * 0.16),
            FadeIn(challenge, shift=UP * 0.16),
            marker.animate.move_to(challenge_bar.get_left() + RIGHT * 0.35),
            lag_ratio=0.08,
        ),
        run_time=min(0.82, max(0.54, duration * 0.12)),
    )
    scene.play(
        marker.animate.move_to(challenge_bar.get_right() + LEFT * 0.35),
        run_time=min(0.66, max(0.42, duration * 0.09)),
        rate_func=smooth,
    )
    lecun_wait_until(scene, origin, duration)
    scene.wait(0.18)


def technology_visual_swap(scene, old, new, run_time):
    old_parts = list(old.submobjects)
    new_parts = list(new.submobjects)
    scene.play(
        semantic_visual_swap(old, new),
        run_time=run_time,
    )
    scene.remove(old, *old_parts, *new_parts)
    scene.add(new)


def construct_technology_adolescence(scene, items):
    """Typed hook, persistent title, then only source-timed one-shot reveals."""
    title = technology_title_center()
    first_duration = float(items[0]["duration_seconds"])
    first_origin = scene.time
    first_end = first_origin + first_duration
    scene.play(
        Write(title),
        run_time=min(1.55, max(1.05, first_duration * 0.28)),
    )
    if scene.time < first_origin + min(1.82, first_duration * 0.34):
        scene.wait(
            first_origin
            + min(1.82, first_duration * 0.34)
            - scene.time
        )
    scene.play(
        Transform(title, technology_title_header()),
        run_time=min(0.72, max(0.48, first_duration * 0.13)),
    )

    first_item = items[0]
    first_captions = first_item.get("params", {}).get("captions", [])
    first_text = (
        first_captions[0]["text"]
        if first_captions
        else first_item["body"]
    )
    visual_phase = narration_visual_phase(0, first_text)
    current_visual = stage_visual(0, phase=visual_phase)
    scene.play(
        FadeIn(current_visual),
        run_time=min(0.46, max(0.30, first_duration * 0.08)),
    )
    current_caption = None

    for cue in first_captions[1:]:
        target_time = first_origin + float(cue["start_seconds"])
        if scene.time < target_time:
            scene.wait(target_time - scene.time)
        replacement = technology_caption(cue["text"])
        cue_duration = (
            float(cue["end_seconds"])
            - float(cue["start_seconds"])
        )
        target_phase = max(
            visual_phase,
            narration_visual_phase(0, cue["text"]),
        )
        if target_phase > visual_phase:
            updated_visual = stage_visual(0, phase=target_phase)
            old_parts = list(current_visual.submobjects)
            new_parts = list(updated_visual.submobjects)
            scene.play(
                AnimationGroup(
                    semantic_visual_swap(current_visual, updated_visual),
                    technology_caption_swap(
                        current_caption,
                        replacement,
                    ),
                    lag_ratio=0.02,
                ),
                run_time=min(0.58, max(0.34, cue_duration * 0.36)),
            )
            scene.remove(
                current_visual,
                *old_parts,
                *new_parts,
            )
            scene.add(updated_visual)
            current_visual = updated_visual
            visual_phase = target_phase
        else:
            scene.play(
                technology_caption_swap(current_caption, replacement),
                run_time=min(0.24, max(0.16, cue_duration * 0.18)),
            )
        current_caption = replacement
    if scene.time < first_end:
        scene.wait(first_end - scene.time)

    for stage, item in enumerate(items[1:], start=1):
        beat_origin = scene.time
        duration = float(item["duration_seconds"])
        beat_end = beat_origin + duration
        captions = item.get("params", {}).get("captions", [])
        initial_text = captions[0]["text"] if captions else item["body"]
        visual_phase = narration_visual_phase(stage, initial_text)
        next_visual = stage_visual(stage, phase=visual_phase)
        next_caption = technology_caption(initial_text)
        old_parts = list(current_visual.submobjects)
        new_parts = list(next_visual.submobjects)
        scene.play(
            AnimationGroup(
                semantic_visual_swap(current_visual, next_visual),
                technology_caption_swap(current_caption, next_caption),
                lag_ratio=0.02,
            ),
            run_time=min(0.58, max(0.40, duration * 0.09)),
        )
        scene.remove(current_visual, *old_parts, *new_parts)
        scene.add(next_visual)
        current_visual = next_visual
        current_caption = next_caption

        for cue in captions[1:]:
            target_time = beat_origin + float(cue["start_seconds"])
            if scene.time < target_time:
                scene.wait(target_time - scene.time)
            replacement = technology_caption(cue["text"])
            cue_duration = (
                float(cue["end_seconds"])
                - float(cue["start_seconds"])
            )
            target_phase = max(
                visual_phase,
                narration_visual_phase(stage, cue["text"]),
            )
            if target_phase > visual_phase:
                updated_visual = stage_visual(
                    stage,
                    phase=target_phase,
                )
                old_parts = list(current_visual.submobjects)
                new_parts = list(updated_visual.submobjects)
                scene.play(
                    AnimationGroup(
                        semantic_visual_swap(
                            current_visual,
                            updated_visual,
                        ),
                        technology_caption_swap(
                            current_caption,
                            replacement,
                        ),
                        lag_ratio=0.02,
                    ),
                    run_time=min(
                        0.58,
                        max(0.34, cue_duration * 0.36),
                    ),
                )
                scene.remove(
                    current_visual,
                    *old_parts,
                    *new_parts,
                )
                scene.add(updated_visual)
                current_visual = updated_visual
                visual_phase = target_phase
            else:
                scene.play(
                    technology_caption_swap(
                        current_caption,
                        replacement,
                    ),
                    run_time=min(
                        0.24,
                        max(0.16, cue_duration * 0.18),
                    ),
                )
            current_caption = replacement
        if scene.time < beat_end:
            scene.wait(beat_end - scene.time)
    scene.wait(0.35)


class ContentMaxxerScene(Scene):
    def construct(self):
        self.camera.background_color = SPEC["background"]
        self.add(background_texture())
        if STORY.get("kind") == "elastic_llm_nesting":
            construct_elastic_llm_nesting(
                self,
                SPEC["primitives"],
            )
            return
        if STORY.get("kind") == "lecun_world_model_bet":
            construct_lecun_world_model_bet(
                self,
                SPEC["primitives"],
            )
            return
        if STORY.get("kind") == "technology_adolescence":
            construct_technology_adolescence(
                self,
                SPEC["primitives"],
            )
            return
        items = SPEC["primitives"]
        current_visual = None
        current_title = None
        current_source = None
        current_source_name = None
        current_caption = None

        style_names = {
            "hand_drawn": "CHALK MECHANISM",
            "whiteboard": "WHITEBOARD STUDY",
            "warm_papyrus": "INVENTOR'S FOLIO",
            "future_minimal": "FRONTIER SIGNAL",
            "director_cut": "EDITORIAL CUT",
        }
        style_mark = tiny_label(style_names[STYLE], [-3.0, 6.78, 0], color=P["muted"], size=16)
        progress = Line([-3.98, 6.45, 0], [-3.98, -6.65, 0], color=P["a"], stroke_width=3, stroke_opacity=0.28)
        self.add(style_mark, progress)

        for stage, item in enumerate(items):
            duration = float(item["duration_seconds"])
            beat_origin = self.time
            beat_end = beat_origin + duration
            recap_played = False
            persistent_header = (
                STORY.get("text_transition_mode")
                == "persistent_lesson_header_handwritten_captions"
            )
            captions = item.get("params", {}).get("captions", [])
            initial_caption_text = captions[0]["text"] if captions else item["body"]
            visual_phase = narration_visual_phase(stage, initial_caption_text)
            if STORY.get("kind") == "mechanism_bayes" and stage in {2, 3} and len(captions) <= 1:
                visual_phase = 1
            visual = stage_visual(stage, phase=visual_phase)
            title_value = (
                STORY.get("hook_title", {}).get("text", item["title"])
                if persistent_header
                else item["title"]
            )
            title = headline_text(title_value)
            active_source_name = source_name(item)
            source = tiny_label(active_source_name, [0, 4.95, 0], color=P["muted"], size=17)
            first_caption = caption_text(captions[0]["text"] if captions else item["body"])
            marker_y = 6.25 - 12.55 * ((stage + 1) / max(1, len(items)))
            marker = Dot([-3.98, marker_y, 0], radius=0.055, color=P["a"])

            if current_visual is None:
                self.play(
                    LaggedStart(
                        Write(title),
                        FadeIn(source, shift=UP * 0.08),
                        Create(visual),
                        FadeIn(first_caption, shift=UP * 0.12),
                        lag_ratio=0.12,
                    ),
                    run_time=min(1.05, duration * 0.28),
                )
                current_visual = visual
                current_title = title
                current_source = source
                current_source_name = active_source_name
                current_caption = first_caption
            else:
                semantic_continuity = STORY.get("transition_mode") == "semantic_continuity"
                old_visual_parts = list(current_visual.submobjects)
                new_visual_parts = list(visual.submobjects)
                transition_animations = [
                    semantic_visual_swap(current_visual, visual),
                    caption_swap(current_caption, first_caption),
                    FadeIn(marker, scale=0.5),
                ]
                if not persistent_header:
                    transition_animations.insert(0, clean_swap(current_title, title))
                if active_source_name != current_source_name:
                    transition_animations.append(clean_swap(current_source, source))
                self.play(
                    AnimationGroup(
                        *transition_animations,
                        lag_ratio=0.04,
                    ),
                    run_time=min(0.9, duration * 0.24),
                )
                if semantic_continuity:
                    self.remove(current_visual, *old_visual_parts, *new_visual_parts)
                    self.add(visual)
                current_visual = visual
                if not persistent_header:
                    current_title = title
                if active_source_name != current_source_name:
                    current_source = source
                    current_source_name = active_source_name
                current_caption = first_caption

            for caption_index, cue in enumerate(captions[1:], start=1):
                target_time = beat_origin + float(cue["start_seconds"])
                if self.time < target_time:
                    wait_with_story_motion(
                        self,
                        current_visual,
                        stage,
                        target_time - self.time,
                    )
                replacement = caption_text(cue["text"])
                cue_duration = float(cue["end_seconds"]) - float(cue["start_seconds"])
                target_phase = max(visual_phase, narration_visual_phase(stage, cue["text"]))
                if target_phase > visual_phase:
                    updated_visual = stage_visual(stage, phase=target_phase)
                    old_visual_parts = list(current_visual.submobjects)
                    new_visual_parts = list(updated_visual.submobjects)
                    self.play(
                        AnimationGroup(
                            semantic_visual_swap(current_visual, updated_visual),
                            caption_swap(current_caption, replacement),
                            lag_ratio=0.03,
                        ),
                        run_time=min(0.65, max(0.42, cue_duration * 0.55)),
                    )
                    self.remove(current_visual, *old_visual_parts, *new_visual_parts)
                    self.add(updated_visual)
                    current_visual = updated_visual
                    visual_phase = target_phase
                else:
                    caption_change = caption_swap(current_caption, replacement)
                    caption_swap_run_time = caption_swap_duration(cue_duration)
                    caption_change.set_run_time(caption_swap_run_time)
                    emphasis_start = cue.get("emphasis_start_seconds")
                    emphasis = (
                        narration_visual_emphasis(
                            current_visual,
                            cue.get("emphasis_text", cue["text"]),
                        )
                        if emphasis_start is not None
                        else None
                    )
                    is_final_recap_caption = (
                        STORY.get("recap_mode") == "full_route_sweep"
                        and stage == len(items) - 1
                        and caption_index == len(captions) - 1
                    )
                    if is_final_recap_caption:
                        recap_run_time = min(
                            1.6,
                            max(0.72, beat_end - self.time - 0.08),
                        )
                        recap_token, recap_animation = (
                            process_recap_animation(
                                current_visual,
                                recap_run_time,
                            )
                        )
                        animations = [caption_change, recap_animation]
                        if emphasis is not None:
                            emphasis_run_time = (
                                min(0.76, max(0.46, cue_duration * 0.48))
                                if STYLE == "future_minimal"
                                else min(
                                    0.58,
                                    max(0.34, cue_duration * 0.38),
                                )
                            )
                            emphasis.set_run_time(emphasis_run_time)
                            emphasis_time = beat_origin + float(
                                emphasis_start
                            )
                            emphasis_delay = max(
                                0.0,
                                emphasis_time - target_time,
                            )
                            animations.append(
                                Succession(
                                    Wait(emphasis_delay),
                                    emphasis,
                                )
                            )
                        self.add(recap_token)
                        self.play(
                            AnimationGroup(
                                *animations,
                                lag_ratio=0.0,
                            )
                        )
                        self.remove(recap_token)
                        recap_played = True
                    elif emphasis is None:
                        self.play(caption_change)
                    else:
                        emphasis_run_time = (
                            min(0.76, max(0.46, cue_duration * 0.48))
                            if STYLE == "future_minimal"
                            else min(0.58, max(0.34, cue_duration * 0.38))
                        )
                        emphasis.set_run_time(emphasis_run_time)
                        emphasis_time = beat_origin + float(emphasis_start)
                        emphasis_delay = max(0.0, emphasis_time - target_time)
                        if emphasis_delay <= caption_swap_run_time:
                            self.play(
                                AnimationGroup(
                                    caption_change,
                                    Succession(Wait(emphasis_delay), emphasis),
                                    lag_ratio=0.0,
                                )
                            )
                        else:
                            self.play(caption_change)
                            if self.time < emphasis_time:
                                self.wait(emphasis_time - self.time)
                            self.play(emphasis)
                current_caption = replacement

            if self.time < beat_end:
                remaining = beat_end - self.time
                if (
                    STORY.get("recap_mode") == "full_route_sweep"
                    and stage == len(items) - 1
                    and not recap_played
                    and remaining >= 0.95
                ):
                    recap_lead = min(0.34, remaining * 0.18)
                    recap_run_time = min(
                        1.35,
                        max(0.72, remaining * 0.62),
                    )
                    recap_tail = max(
                        0.0,
                        remaining - recap_lead - recap_run_time,
                    )
                    if recap_lead > 0:
                        self.wait(recap_lead)
                    play_process_recap(
                        self,
                        current_visual,
                        recap_run_time,
                    )
                    if recap_tail > 0:
                        self.wait(recap_tail)
                elif recap_played:
                    wait_with_story_motion(
                        self,
                        current_visual,
                        stage,
                        remaining,
                    )
                else:
                    wait_with_story_motion(
                        self,
                        current_visual,
                        stage,
                        remaining,
                    )

        self.wait(0.35)
'''


def _scene_source(spec: ManimSceneSpec) -> str:
    payload = json.dumps(
        {
            "background": spec.background,
            "animation_style": spec.animation_style,
            "story": spec.story,
            "primitives": [
                {
                    "kind": item.kind,
                    "title": item.title,
                    "body": item.body,
                    "source_label": item.source_label,
                    "duration_seconds": item.duration_seconds,
                    "params": item.params,
                }
                for item in spec.primitives
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    technology_image_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "reference-images"
        / "nersc-server-racks-cc0.jpg"
    ).resolve()
    lecun_portrait_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "reference-images"
        / "yann-lecun-2025-cc-by-sa.jpg"
    ).resolve()
    earth_image_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "reference-images"
        / "nasa-earth-western-hemisphere-public-domain.jpg"
    ).resolve()
    header = f'''# Generated by contentmaxxer animation director.
import json
import textwrap
import numpy as np
from manim import *

config.pixel_width = {spec.width}
config.pixel_height = {spec.height}
config.frame_rate = {spec.fps}
config.frame_width = 9
config.frame_height = 16
SPEC = json.loads({payload!r})
TECHNOLOGY_IMAGE_PATH = {str(technology_image_path)!r}
LECUN_PORTRAIT_PATH = {str(lecun_portrait_path)!r}
EARTH_IMAGE_PATH = {str(earth_image_path)!r}
INK = "#F4F7FB"
MUTED = "#A8B3C4"
ACCENT = "#5EEAD4"
PANEL = "#122238"
PANEL_2 = "#0B1829"
WARM = "#FBBF24"
PINK = "#FB7185"

'''
    use_hand_drawn_library = (
        spec.animation_style == "hand_drawn"
        and spec.story.get("kind") not in {"causal_explainer", "mechanism_handshake"}
    )
    library = HAND_DRAWN_SCENE_LIBRARY if use_hand_drawn_library else STYLE_EXPERIMENT_SCENE_LIBRARY
    return header + library


def write_scene_py(job_dir: Path, spec: ManimSceneSpec) -> Path:
    path = job_dir / "video" / "manim" / "scene.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_scene_source(spec), encoding="utf-8")
    return path


def manim_available() -> bool:
    return importlib.util.find_spec("manim") is not None or shutil.which("manim") is not None


def render_manim(scene_path: Path, output_path: Path) -> Tuple[Path, str]:
    if not manim_available():
        raise RuntimeError("Manim is not installed. Install Manim or use --renderer auto|raster.")
    media_dir = output_path.parent / "manim_media"
    command = [sys.executable, "-m", "manim", str(scene_path), "ContentMaxxerScene", "-qh", "--media_dir", str(media_dir)]
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-2000:]
        raise RuntimeError(f"Manim render failed: {detail}")
    candidates = sorted(media_dir.rglob("ContentMaxxerScene.mp4"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise RuntimeError("Manim completed but did not produce ContentMaxxerScene.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidates[-1], output_path)
    return output_path, " ".join(command)
