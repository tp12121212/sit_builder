from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from app.models import FilterType, LogicType, SitElement, SitElementGroup, SitFilter, SitGroupElement


@dataclass
class ElementMatch:
    element_id: str
    element_role: str
    value: str
    start: int
    end: int


def _iter_element_patterns(element: SitElement) -> Iterable[str]:
    if not element.pattern:
        return []

    if element.element_type in {"KEYWORD_LIST", "DICTIONARY"}:
        try:
            parsed = json.loads(element.pattern)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [part.strip() for part in element.pattern.split(",") if part.strip()]

    return [element.pattern]


def _find_matches(text: str, element: SitElement) -> list[ElementMatch]:
    flags = 0 if element.case_sensitive else re.IGNORECASE
    results: list[ElementMatch] = []

    for pattern in _iter_element_patterns(element):
        if element.element_type == "REGEX":
            try:
                compiled = re.compile(pattern, flags)
            except re.error:
                continue
            for hit in compiled.finditer(text):
                results.append(
                    ElementMatch(
                        element_id=str(element.element_id),
                        element_role=element.element_role,
                        value=hit.group(0),
                        start=hit.start(),
                        end=hit.end(),
                    )
                )
        else:
            search = pattern if element.case_sensitive else pattern.lower()
            source = text if element.case_sensitive else text.lower()
            idx = source.find(search)
            while idx != -1:
                results.append(
                    ElementMatch(
                        element_id=str(element.element_id),
                        element_role=element.element_role,
                        value=text[idx : idx + len(pattern)],
                        start=idx,
                        end=idx + len(pattern),
                    )
                )
                idx = source.find(search, idx + len(pattern))

    return results


def _passes_filters(text: str, value: str, filters: list[SitFilter]) -> bool:
    include_patterns = [flt.pattern for flt in filters if flt.filter_type == FilterType.INCLUDE]
    exclude_patterns = [flt.pattern for flt in filters if flt.filter_type == FilterType.EXCLUDE]

    if include_patterns:
        include_ok = any(re.search(pattern, text, re.IGNORECASE) for pattern in include_patterns)
        if not include_ok:
            return False

    if any(re.search(pattern, value, re.IGNORECASE) for pattern in exclude_patterns):
        return False

    return True


def _group_logic_satisfied(
    text: str,
    primary: ElementMatch,
    elements_by_id: dict[str, SitElement],
    groups: list[SitElementGroup],
    group_links: list[SitGroupElement],
) -> bool:
    if not groups:
        return True

    group_to_elements: dict[str, list[str]] = {}
    for link in group_links:
        group_to_elements.setdefault(str(link.group_id), []).append(str(link.element_id))

    for group in groups:
        element_ids = group_to_elements.get(str(group.group_id), [])
        if not element_ids:
            continue

        hits = 0
        for element_id in element_ids:
            element = elements_by_id.get(element_id)
            if element is None:
                continue

            for match in _find_matches(text, element):
                if abs(match.start - primary.start) <= group.proximity_window_chars:
                    hits += 1
                    break

        if group.logic_type == LogicType.AND and hits < len(element_ids):
            return False
        if group.logic_type == LogicType.OR and hits < 1:
            return False
        if group.logic_type == LogicType.THRESHOLD and hits < (group.threshold_count or 1):
            return False

    return True


def test_sit(
    text: str,
    confidence_level: int,
    elements: list[SitElement],
    groups: list[SitElementGroup],
    group_links: list[SitGroupElement],
    filters: list[SitFilter],
) -> list[dict]:
    elements_by_id = {str(element.element_id): element for element in elements}

    primary_elements = [element for element in elements if element.element_role == "PRIMARY"]
    matches: list[dict] = []

    for element in primary_elements:
        for primary_hit in _find_matches(text, element):
            if not _passes_filters(text, primary_hit.value, filters):
                continue
            if not _group_logic_satisfied(text, primary_hit, elements_by_id, groups, group_links):
                continue

            matches.append(
                {
                    "value": primary_hit.value,
                    "position": primary_hit.start,
                    "confidence": confidence_level,
                    "matched_elements": [{"element_id": primary_hit.element_id, "element_role": primary_hit.element_role}],
                    "matched_groups": [
                        {
                            "group_id": str(group.group_id),
                            "group_name": group.group_name or "",
                        }
                        for group in groups
                    ],
                }
            )

    return matches
