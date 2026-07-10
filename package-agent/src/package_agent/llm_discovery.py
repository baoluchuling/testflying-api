from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class LlmAdapter:
    name: str
    executable: str


Which = Callable[[str], str | None]


def discover_llm_adapter(which: Which = shutil.which) -> LlmAdapter | None:
    for executable, name in (
        ("codex", "codex_cli"),
        ("claude", "claude_cli"),
        ("llm-runtime", "llm_runtime"),
    ):
        resolved = which(executable)
        if resolved:
            return LlmAdapter(name=name, executable=resolved)
    return None
