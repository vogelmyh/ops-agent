"""TTY helpers for the interactive demo presenter."""

from __future__ import annotations


def rule(char: str = "═", width: int = 52) -> str:
    return char * width


def heading(title: str) -> None:
    print(f"\n{rule()}")
    print(f"  {title}")
    print(rule())


def pause_enter(hint: str = "按 Enter 继续…") -> None:
    try:
        input(f"  ⏸  {hint} ")
    except EOFError:
        print("  (非交互终端，自动继续)")


def prompt_yes_no(question: str, *, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    try:
        raw = input(f"  ? {question} [{suffix}] ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in {"y", "yes", "是"}


def prompt_choice(prompt: str, choices: dict[str, str]) -> str | None:
    """Return choice key, or None for quit/back when user picks 0/q."""
    keys = list(choices.keys())
    for i, key in enumerate(keys, start=1):
        print(f"    {i}. {choices[key]}")
    print("    0. 返回")
    try:
        raw = input(f"  {prompt} ").strip()
    except EOFError:
        return None
    if raw in {"0", "q", "b", ""}:
        return None
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(keys):
            return keys[idx]
    if raw in choices:
        return raw
    print("  无效选择，请重试。")
    return prompt_choice(prompt, choices)
