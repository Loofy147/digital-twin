from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=120)


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class AnswerInput(BaseModel):
    question_id: str
    value: float = Field(ge=1, le=5)


class AssessmentSubmit(BaseModel):
    answers: list[AnswerInput] = Field(min_length=1, max_length=200)


class ConsentInput(BaseModel):
    purpose: str = Field(min_length=2, max_length=120)
    provider: str | None = Field(default=None, max_length=80)
    granted: bool
    policy_version: str = Field(min_length=1, max_length=40)


class ScenarioInput(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    context: dict[str, Any] = Field(default_factory=dict)


class TrainingInput(BaseModel):
    idempotency_key: str = Field(min_length=4, max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class DimensionScore:
    key: str
    label: str
    score: float
    confidence: float
    evidence: list[str]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def infer_dimensions(dimensions: list[dict[str, Any]], questions: list[dict[str, Any]], answers: dict[str, float]) -> list[DimensionScore]:
    by_dimension: dict[str, list[tuple[dict[str, Any], float]]] = {}
    for q in questions:
        if q["id"] in answers:
            by_dimension.setdefault(q["dimension_key"], []).append((q, answers[q["id"]]))
    result: list[DimensionScore] = []
    for d in dimensions:
        observations = by_dimension.get(d["key"], [])
        if not observations:
            result.append(DimensionScore(d["key"], d["label"], 0.5, 0.0, []))
            continue
        score = sum((value - 1.0) / 4.0 for _, value in observations) / len(observations)
        confidence = clamp(0.35 + 0.15 * len(observations), 0.0, 0.95)
        evidence = [f"Assessment response: {q['prompt']} ({value:.0f}/5)" for q, value in observations]
        result.append(DimensionScore(d["key"], d["label"], round(score, 4), round(confidence, 4), evidence))
    return result


def scenario_recommendation(prompt: str, scores: list[DimensionScore]) -> dict[str, Any]:
    ranked = sorted(scores, key=lambda x: x.score, reverse=True)
    strengths = [s.label for s in ranked[:3] if s.confidence > 0]
    low = [s.label for s in ranked[-2:] if s.confidence > 0]
    return {
        "summary": "A baseline simulation based on the current self-reported profile.",
        "recommended_next_step": f"Break the situation into a reversible experiment and review the outcome after a defined checkpoint. Prompt: {prompt}",
        "likely_strengths": strengths,
        "watchouts": low,
        "confidence": round(sum(s.confidence for s in scores) / max(len(scores), 1), 4),
        "model_limitations": ["This is an interpretable heuristic, not a factual prediction.", "The result reflects available consented inputs and may be incomplete."],
        "evidence": [e for s in scores for e in s.evidence][:8],
    }
