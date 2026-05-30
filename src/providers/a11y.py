from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class A11yNode:
    id: str
    role: str
    name: str = ""
    bbox: list[int] = field(default_factory=lambda: [0, 0, 0, 0])  # [x1, y1, x2, y2]
    children: list["A11yNode"] = field(default_factory=list)


@dataclass
class A11yTree:
    root: A11yNode | None = None
    node_count: int = 0
    source: str = "none"


class AccessibilityProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def get_tree(self, max_depth: int = 5, max_nodes: int = 200) -> A11yTree:
        ...


class NullAccessibilityProvider(AccessibilityProvider):
    def is_available(self) -> bool:
        return False

    def get_tree(self, max_depth: int = 5, max_nodes: int = 200) -> A11yTree:
        return A11yTree(node_count=0, source="none")
