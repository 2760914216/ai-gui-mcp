import re


class GdinoLabelMapper:
    _INTERACTIVE_KEYWORDS: tuple[str, ...] = (
        "menu item",
        "button",
        "text",
        "input",
        "check",
        "radio",
        "link",
        "tab",
    )
    _STRUCTURAL_KEYWORDS: tuple[str, ...] = (
        "window",
        "menu",
        "sidebar",
        "toolbar",
        "panel",
        "list",
        "table",
        "dialog",
        "form",
    )
    KNOWN_LABELS: set[str] = set(_INTERACTIVE_KEYWORDS) | set(_STRUCTURAL_KEYWORDS)

    def map(self, label: str | None) -> str:
        if not label:
            return "unknown"

        normalized = label.lower()
        if not normalized.strip():
            return "unknown"

        for keyword in self._INTERACTIVE_KEYWORDS:
            if self._matches(keyword, normalized):
                return "interactive"

        for keyword in self._STRUCTURAL_KEYWORDS:
            if self._matches(keyword, normalized):
                return "structural"

        return "unknown"

    @staticmethod
    def _matches(keyword: str, normalized: str) -> bool:
        if keyword == "tab":
            return re.search(r"\btab\b", normalized) is not None
        return keyword in normalized
