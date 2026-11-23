from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Outcome:
    """The result of one evaluator on one case."""

    name: str
    kind: str                      # "structural" | "exec" | "retrieval" | "judge"
    passed: Optional[bool]         # None = not applicable / skipped (e.g. node not installed)
    detail: str = ""
    score: Optional[float] = None  # 0..1 where a graded score makes sense
    required: bool = True          # a failed required outcome fails the case

    def to_dict(self) -> dict:
        return asdict(self)


def ok(name: str, kind: str = "structural", detail: str = "", **kw) -> Outcome:
    return Outcome(name, kind, True, detail, **kw)


def fail(name: str, detail: str, kind: str = "structural", **kw) -> Outcome:
    return Outcome(name, kind, False, detail, **kw)


def skipped(name: str, detail: str, kind: str = "structural") -> Outcome:
    return Outcome(name, kind, None, detail, required=False)
