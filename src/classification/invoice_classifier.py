from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CLASSIFICATION_THRESHOLD = 0.65
STRONG_MATCH_FLOOR = 0.60
STRONG_MATCH_MARGIN = 0.10


@dataclass(slots=True)
class BlueprintCandidate:
    blueprint: dict[str, Any]
    path: Path
    display_name: str
    blueprint_id: str
    document_type: str | None


@dataclass(slots=True)
class ClassificationResult:
    file_name: str
    status: str
    detected_type: str | None
    blueprint_id: str | None
    confidence: float
    reason: str
    blueprint: dict[str, Any] | None = None
    blueprint_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "status": self.status,
            "detected_type": self.detected_type,
            "blueprint_id": self.blueprint_id,
            "confidence": self.confidence,
            "reason": self.reason,
            "blueprint_path": self.blueprint_path,
        }


class InvoiceClassifier:
    def __init__(self, blueprints: list[BlueprintCandidate], threshold: float = CLASSIFICATION_THRESHOLD) -> None:
        self.blueprints = blueprints
        self.threshold = threshold

    def classify(self, normalized_document: dict[str, Any], file_name: str) -> ClassificationResult:
        if not self.blueprints:
            return ClassificationResult(
                file_name=file_name,
                status="unknown",
                detected_type=None,
                blueprint_id=None,
                confidence=0.0,
                reason="No blueprints are available for classification.",
            )

        text = _normalized_text(normalized_document)
        scored = [self._score_blueprint(text, candidate) for candidate in self.blueprints]
        scored.sort(key=lambda item: item[0], reverse=True)
        best_score, best_candidate, best_reasons = scored[0]
        second_best_score = scored[1][0] if len(scored) > 1 else 0.0

        strong_best_match = (
            best_score >= STRONG_MATCH_FLOOR
            and len(best_reasons) >= 3
            and best_score - second_best_score >= STRONG_MATCH_MARGIN
        )

        if best_score < self.threshold and not strong_best_match:
            return ClassificationResult(
                file_name=file_name,
                status="unknown",
                detected_type=None,
                blueprint_id=None,
                confidence=round(best_score, 2),
                reason="No blueprint matched enough required labels, keywords, or table headers.",
            )

        return ClassificationResult(
            file_name=file_name,
            status="known",
            detected_type=best_candidate.display_name,
            blueprint_id=best_candidate.blueprint_id,
            confidence=round(best_score, 2),
            reason=_reason_sentence(best_reasons, strong_best_match and best_score < self.threshold),
            blueprint=best_candidate.blueprint,
            blueprint_path=str(best_candidate.path),
        )

    def _score_blueprint(self, text: str, candidate: BlueprintCandidate) -> tuple[float, BlueprintCandidate, list[str]]:
        lowered = _clean(text)
        strong_keywords = _layout_keywords(candidate.blueprint)
        required_labels, optional_labels = _field_labels(candidate.blueprint)
        table_headers = _table_headers(candidate.blueprint)

        strong_score, strong_matches = _match_score(lowered, strong_keywords)
        required_score, required_matches = _match_score(lowered, required_labels)
        optional_score, optional_matches = _match_score(lowered, optional_labels)
        table_score, table_matches = _match_score(lowered, table_headers)

        score = (
            strong_score * 0.35
            + required_score * 0.35
            + table_score * 0.2
            + optional_score * 0.1
        )
        if not strong_keywords:
            score = required_score * 0.55 + table_score * 0.3 + optional_score * 0.15
        if strong_matches and required_matches and table_matches:
            score += 0.05

        reasons: list[str] = []
        if strong_matches:
            reasons.append(f"matched layout keywords: {', '.join(strong_matches[:3])}")
        if required_matches:
            reasons.append(f"matched required labels: {', '.join(required_matches[:3])}")
        if table_matches:
            reasons.append(f"matched table headers: {', '.join(table_matches[:3])}")
        if optional_matches and not reasons:
            reasons.append(f"matched supporting labels: {', '.join(optional_matches[:3])}")
        return min(score, 1.0), candidate, reasons


def load_blueprints(paths: list[str | Path]) -> list[BlueprintCandidate]:
    candidates: list[BlueprintCandidate] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        for file_path in files:
            resolved = file_path.resolve()
            if resolved in seen or not file_path.exists():
                continue
            seen.add(resolved)
            blueprint = json.loads(file_path.read_text(encoding="utf-8"))
            candidates.append(_candidate_from_blueprint(blueprint, file_path))
    return candidates


def _candidate_from_blueprint(blueprint: dict[str, Any], path: Path) -> BlueprintCandidate:
    metadata = blueprint.get("blueprint_metadata", {}) if isinstance(blueprint.get("blueprint_metadata"), dict) else {}
    blueprint_id = str(blueprint.get("blueprint_id") or metadata.get("blueprint_id") or path.stem)
    document_family = blueprint.get("document_family")
    document_type = None
    if isinstance(document_family, dict):
        document_type = document_family.get("document_type") or document_family.get("family")
    elif document_family:
        document_type = str(document_family)
    display_name = metadata.get("blueprint_name") or blueprint_id.replace("_blueprint", "").replace("_v1", "")
    return BlueprintCandidate(
        blueprint=blueprint,
        path=path,
        display_name=str(display_name),
        blueprint_id=blueprint_id,
        document_type=document_type,
    )


def _normalized_text(normalized_document: dict[str, Any]) -> str:
    if normalized_document.get("full_text"):
        return str(normalized_document["full_text"])
    lines: list[str] = []
    for page in normalized_document.get("pages", []):
        for line in page.get("lines", []):
            lines.append(str(line.get("text", "")))
    return "\n".join(lines)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def _contains(text: str, token: str) -> bool:
    clean_token = _clean(token)
    if not clean_token:
        return False
    if len(clean_token) <= 2:
        return bool(re.search(rf"(?<!\w){re.escape(clean_token)}:?(?!\w)", text))
    if " " in clean_token:
        return clean_token in text
    return bool(re.search(rf"(?<!\w){re.escape(clean_token)}(?!\w)", text))


def _match_score(text: str, tokens: list[str]) -> tuple[float, list[str]]:
    unique_tokens = list(dict.fromkeys(token for token in tokens if token))
    if not unique_tokens:
        return 0.0, []
    matches = [token for token in unique_tokens if _contains(text, token)]
    return len(matches) / len(unique_tokens), matches


def _layout_keywords(blueprint: dict[str, Any]) -> list[str]:
    layout = blueprint.get("layout_identity", {}) if isinstance(blueprint.get("layout_identity"), dict) else {}
    keywords: list[str] = []
    keywords.extend(layout.get("required_keywords", []))
    keywords.extend(layout.get("optional_keywords", [])[:8])
    signatures = layout.get("layout_signatures", {})
    if isinstance(signatures, dict):
        keywords.extend(signatures.get("common_label_patterns", [])[:8])
    return [str(keyword) for keyword in keywords]


def _field_labels(blueprint: dict[str, Any]) -> tuple[list[str], list[str]]:
    required: list[str] = []
    optional: list[str] = []
    for field in blueprint.get("fields", []):
        labels = [str(label) for label in field.get("possible_labels", [])]
        if field.get("required"):
            required.extend(labels[:3])
        else:
            optional.extend(labels[:2])
    return required, optional


def _table_headers(blueprint: dict[str, Any]) -> list[str]:
    headers: list[str] = []
    for table in blueprint.get("tables", []):
        headers.extend(str(header) for header in table.get("header_keywords", [])[:8])
        headers.extend(str(marker) for marker in table.get("start_markers", [])[:4])
    return headers


def _reason_sentence(reasons: list[str], margin_accepted: bool = False) -> str:
    if not reasons:
        return "Matched this blueprint by overall label and table-header similarity."
    sentence = "; ".join(reasons) + "."
    if margin_accepted:
        sentence += " Accepted as known because it was clearly ahead of the next closest blueprint."
    return sentence
