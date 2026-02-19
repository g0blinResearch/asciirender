#!/usr/bin/env python3
"""
Prompt History Extractor
========================
Extracts the meaningful prompt flow from Kilo Code task history files.

In Kilo Code history files, the conversation follows this pattern:
  1. User sends an initial <task> prompt
  2. Assistant works through many tool exchanges (read files, write code, run commands)
  3. Assistant calls attempt_completion with a result summary
  4. User may provide <feedback> (which acts as the next prompt)
  5. Steps 2-4 repeat

This script extracts:
  - The initial task prompt
  - Each attempt_completion result (shortened)
  - Each user feedback message
  - The number of tool exchanges between each interaction point

Code changes, detailed thinking/reasoning text, and raw tool output are
all stripped to produce a concise, readable history of the development flow.

Usage:
    python3 extract_prompts.py

Output:
    prompt_history.md  -  A markdown file presenting the full prompt history.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ── Configuration ──────────────────────────────────────────────────────────

@dataclass
class FileConfig:
    """Configuration for a single history file to process."""
    path: str
    model_label: str
    session_label: str


FILES_TO_PROCESS: List[FileConfig] = [
    FileConfig(
        path="kilo_code_task_feb-19-2026_9-37-22-am.md",
        model_label="Local MiniMax-M2.5 Cluster",
        session_label="Session 1 - Morning (9:37 AM)",
    ),
    FileConfig(
        path="kilo_code_task_feb-19-2026_12-30-00-pm.md",
        model_label="Local MiniMax-M2.5 Cluster",
        session_label="Session 2 - Afternoon (12:30 PM)",
    ),
    FileConfig(
        path="opus_kilo_code_task_feb-19-2026_2-37-48-pm.md",
        model_label="Opus 4.6",
        session_label="Session 3 - Afternoon (2:37 PM)",
    ),
    FileConfig(
        path="opus_kilo_code_task_feb-19-2026_7-34-40-pm.md",
        model_label="Opus 4.6",
        session_label="Session 4 - Afternoon (7:34 PM)",
    ),
    FileConfig(
        path="opus_kilo_code_task_feb-19-2026_10-36-17-pm.md",
        model_label="Opus 4.6",
        session_label="Session 5 - Afternoon (10:36 PM)",
    ),

]

OUTPUT_FILE = "prompt_history.md"

# Keywords to exclude: any completion step where the result or feedback
# mentions these terms (case-insensitive) will be removed from the output.
# This is useful for filtering out work that was later undone.
EXCLUDE_KEYWORDS: List[str] = [
    "",
]


# ── Data Structures ────────────────────────────────────────────────────────

@dataclass
class CompletionAttempt:
    """An attempt_completion result and the user feedback that followed."""
    result_text: str
    user_feedback: Optional[str] = None
    tool_exchanges_before: int = 0  # tool round-trips between this and previous


@dataclass
class SessionHistory:
    """Extracted history from one session file."""
    config: FileConfig
    initial_task: str = ""
    initial_mode: Optional[str] = None
    completions: List[CompletionAttempt] = field(default_factory=list)
    total_raw_messages: int = 0
    total_tool_exchanges: int = 0
    mode_switches: List[str] = field(default_factory=list)


# ── Parsing ────────────────────────────────────────────────────────────────

def split_into_messages(text: str) -> List[Tuple[str, str]]:
    """Split raw markdown into (role, content) pairs."""
    messages = []
    parts = re.split(r'^---\s*$', text, flags=re.MULTILINE)

    current_role = None
    current_content = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith("**User:**"):
            if current_role is not None:
                messages.append((current_role, "\n".join(current_content).strip()))
            current_role = "user"
            content = re.sub(r'^\*\*User:\*\*\s*', '', part, count=1)
            current_content = [content]
        elif part.startswith("**Assistant:**"):
            if current_role is not None:
                messages.append((current_role, "\n".join(current_content).strip()))
            current_role = "assistant"
            content = re.sub(r'^\*\*Assistant:\*\*\s*', '', part, count=1)
            current_content = [content]
        else:
            if current_role is not None:
                current_content.append(part)

    if current_role is not None:
        messages.append((current_role, "\n".join(current_content).strip()))

    return messages


def extract_task_text(content: str) -> Optional[str]:
    """Extract text from <task>...</task> tags."""
    match = re.search(r'<task>\s*(.*?)\s*</task>', content, re.DOTALL)
    return match.group(1).strip() if match else None


def extract_mode(content: str) -> Optional[str]:
    """Extract mode from <slug>...</slug> in environment details."""
    match = re.search(r'<slug>(.*?)</slug>', content)
    return match.group(1).strip() if match else None


def extract_feedback(content: str) -> Optional[str]:
    """Extract user feedback from <feedback>...</feedback> tags."""
    match = re.search(r'<feedback>\s*(.*?)\s*</feedback>', content, re.DOTALL)
    return match.group(1).strip() if match else None


def extract_completion_result(content: str) -> Optional[str]:
    """Extract the result text from an attempt_completion tool use, shortened."""
    # Pattern: Result: <text until end of block or next section>
    match = re.search(r'Result:\s*(.*?)(?=\n\n\[|\n\n\*Tools|\Z)', content, re.DOTALL)
    if match:
        result = match.group(1).strip()
        # Clean up markdown link syntax for readability
        result = re.sub(r'\[`([^`]+)`\]\([^)]+\)', r'`\1`', result)
        result = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', result)
        # Strip code blocks from result text
        result = re.sub(r'```[\s\S]*?```', '', result)
        # Strip long bullet-point lists (keep first 5 items)
        lines = result.split('\n')
        bullet_count = 0
        filtered_lines = []
        skipped_bullets = 0
        for line in lines:
            if re.match(r'^\s*[-*•]\s', line):
                bullet_count += 1
                if bullet_count <= 5:
                    filtered_lines.append(line)
                else:
                    skipped_bullets += 1
            else:
                if skipped_bullets > 0:
                    filtered_lines.append(f"  *(... {skipped_bullets} more items)*")
                    skipped_bullets = 0
                bullet_count = 0
                filtered_lines.append(line)
        if skipped_bullets > 0:
            filtered_lines.append(f"  *(... {skipped_bullets} more items)*")
        result = '\n'.join(filtered_lines)
        # Collapse multiple blank lines
        result = re.sub(r'\n{3,}', '\n\n', result).strip()
        # Final truncation at 800 chars
        if len(result) > 800:
            truncated = result[:800]
            cut = max(truncated.rfind('.'), truncated.rfind('\n'))
            if cut > 400:
                truncated = truncated[:cut + 1]
            result = truncated.rstrip() + "\n\n*(truncated)*"
        return result
    return None


def is_tool_result(content: str) -> bool:
    """Check if a user message is an automatic tool result."""
    cleaned = re.sub(
        r'<environment_details>.*?</environment_details>',
        '', content, flags=re.DOTALL
    ).strip()
    return cleaned.startswith("[Tool")


def is_error_message(content: str) -> bool:
    """Check if a user message is a system error."""
    cleaned = re.sub(
        r'<environment_details>.*?</environment_details>',
        '', content, flags=re.DOTALL
    ).strip()
    return cleaned.startswith("[ERROR]")


def has_feedback(content: str) -> bool:
    """Check if a user message contains feedback tags."""
    return '<feedback>' in content


def extract_mode_switches(messages: List[Tuple[str, str]]) -> List[str]:
    """Find all mode switches in the conversation."""
    modes = []
    for role, content in messages:
        if role == "assistant" and "switch_mode" in content:
            mode_match = re.search(r'Mode_slug:\s*(\w+)', content)
            if mode_match:
                modes.append(mode_match.group(1))
    return modes


def parse_file(config: FileConfig) -> SessionHistory:
    """Parse a single history file into structured session data."""
    print(f"  Parsing: {config.path} ({config.model_label})...")

    if not os.path.exists(config.path):
        print(f"  WARNING: File not found: {config.path}")
        return SessionHistory(config=config)

    with open(config.path, 'r', encoding='utf-8') as f:
        text = f.read()

    messages = split_into_messages(text)
    session = SessionHistory(config=config, total_raw_messages=len(messages))

    # Extract initial task from first user message
    if messages and messages[0][0] == "user":
        task_text = extract_task_text(messages[0][1])
        if task_text:
            session.initial_task = task_text
        session.initial_mode = extract_mode(messages[0][1])

    # Extract mode switches
    session.mode_switches = extract_mode_switches(messages)

    # Walk through messages and find completion/feedback cycles
    tool_count = 0
    total_tool = 0

    for i, (role, content) in enumerate(messages):
        if role == "user" and (is_tool_result(content) or is_error_message(content)):
            tool_count += 1
            total_tool += 1
            continue

        if role == "assistant" and "attempt_completion" in content:
            result_text = extract_completion_result(content)
            if result_text is None:
                result_text = "(completion result not extracted)"

            # Look ahead for user feedback
            feedback = None
            if i + 1 < len(messages) and messages[i + 1][0] == "user":
                next_content = messages[i + 1][1]
                feedback = extract_feedback(next_content)
                if feedback is None and has_feedback(next_content):
                    feedback = "(feedback text not extracted)"

            completion = CompletionAttempt(
                result_text=result_text,
                user_feedback=feedback,
                tool_exchanges_before=tool_count,
            )
            session.completions.append(completion)
            tool_count = 0

    session.total_tool_exchanges = total_tool
    print(f"  Found {len(session.completions)} completion attempts, "
          f"{total_tool} tool exchanges, {len(messages)} raw messages")
    return session


def filter_excluded_steps(session: SessionHistory) -> int:
    """Remove completion steps that match EXCLUDE_KEYWORDS.

    A step is excluded if any keyword appears (case-insensitive) in either
    the result text or the user feedback. The tool_exchanges_before count
    of excluded steps is absorbed into the next remaining step.

    Returns the number of steps removed.
    """
    if not EXCLUDE_KEYWORDS:
        return 0

    patterns = [kw.lower() for kw in EXCLUDE_KEYWORDS]
    original_count = len(session.completions)
    filtered = []
    absorbed_tools = 0

    for comp in session.completions:
        combined = (comp.result_text + " " + (comp.user_feedback or "")).lower()
        if any(pat in combined for pat in patterns):
            # Absorb this step's tool exchanges into the carry-forward count
            absorbed_tools += comp.tool_exchanges_before
            session.total_tool_exchanges -= comp.tool_exchanges_before
        else:
            # Carry forward any absorbed tool exchanges
            comp.tool_exchanges_before += absorbed_tools
            absorbed_tools = 0
            filtered.append(comp)

    removed = original_count - len(filtered)
    session.completions = filtered
    if removed > 0:
        print(f"  Filtered out {removed} steps matching keywords: {EXCLUDE_KEYWORDS}")
    return removed


# ── Markdown Generation ───────────────────────────────────────────────────

def make_anchor(text: str) -> str:
    """Convert heading text to GitHub/VS Code-style anchor.

    Most renderers: lowercase, strip non-alphanumeric (except space/hyphen),
    spaces → hyphens. Multiple consecutive hyphens are NOT collapsed.
    """
    anchor = text.lower()
    # Remove special chars (em-dash, parens, colons, etc.)
    anchor = re.sub(r'[^\w\s-]', '', anchor)
    # Spaces to hyphens
    anchor = re.sub(r'\s+', '-', anchor)
    # Do NOT collapse multiple hyphens — matches GitHub behaviour
    return anchor.strip('-')


def generate_markdown(sessions: List[SessionHistory]) -> str:
    """Generate the output markdown document."""
    lines = []

    # Header
    lines.append("# Prompt History Summary")
    lines.append("")
    lines.append("**Project:** ASCII 3D Spinning Cube  ")
    lines.append("**Date:** 19 February 2026  ")
    lines.append("**Tool:** Kilo Code (VS Code extension)  ")
    lines.append("")
    lines.append("This document presents the prompt history across three development sessions,")
    lines.append("extracted from Kilo Code task history files. Code changes, detailed thinking/")
    lines.append("reasoning text, and raw tool output have been stripped. What remains is the")
    lines.append("sequence of **user prompts** (initial tasks + feedback) and **assistant")
    lines.append("completion summaries**, showing how the project evolved through iterative")
    lines.append("development.")
    lines.append("")

    # Summary stats
    total_completions = sum(len(s.completions) for s in sessions)
    total_raw = sum(s.total_raw_messages for s in sessions)
    total_tools = sum(s.total_tool_exchanges for s in sessions)
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Sessions | {len(sessions)} |")
    lines.append(f"| Total completion attempts | {total_completions} |")
    lines.append(f"| Total raw messages | {total_raw:,} |")
    lines.append(f"| Total tool exchanges | {total_tools:,} |")
    lines.append("")

    # Table of contents
    lines.append("## Sessions")
    lines.append("")
    for i, session in enumerate(sessions, 1):
        anchor = make_anchor(session.config.session_label)
        lines.append(
            f"{i}. [{session.config.session_label}](#{anchor}) — "
            f"**{session.config.model_label}** "
            f"({len(session.completions)} completions)"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Each session
    for session in sessions:
        lines.append(f"## {session.config.session_label}")
        lines.append("")
        lines.append(f"| Property | Value |")
        lines.append(f"|----------|-------|")
        lines.append(f"| **Model** | {session.config.model_label} |")
        lines.append(f"| **Source file** | `{session.config.path}` |")
        lines.append(f"| **Initial mode** | `{session.initial_mode or 'unknown'}` |")
        lines.append(f"| **Completion attempts** | {len(session.completions)} |")
        lines.append(f"| **Tool exchanges** | {session.total_tool_exchanges} |")
        lines.append(f"| **Raw messages** | {session.total_raw_messages} |")
        if session.mode_switches:
            lines.append(f"| **Mode switches** | {' → '.join(session.mode_switches)} |")
        lines.append("")

        # Initial task
        lines.append("### Initial Task")
        lines.append("")
        lines.append(f"> {session.initial_task}")
        lines.append("")

        # Completion/feedback cycle
        for j, comp in enumerate(session.completions, 1):
            lines.append(f"### Step {j}")
            lines.append("")

            if comp.tool_exchanges_before > 0:
                lines.append(f"*({comp.tool_exchanges_before} tool exchanges)*")
                lines.append("")

            lines.append(f"**✅ Completion Result:**")
            lines.append("")
            # Indent result as blockquote
            for line in comp.result_text.split('\n'):
                lines.append(f"> {line}")
            lines.append("")

            if comp.user_feedback:
                lines.append(f"**💬 User Feedback:**")
                lines.append("")
                for line in comp.user_feedback.split('\n'):
                    lines.append(f"> {line}")
                lines.append("")
            else:
                lines.append("*✓ Accepted (no further feedback)*")
                lines.append("")

            lines.append("---")
            lines.append("")

        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by `extract_prompts.py` — prompt history extraction script.*")
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Prompt History Extractor")
    print("=" * 40)
    print()

    sessions = []
    total_filtered = 0
    for config in FILES_TO_PROCESS:
        session = parse_file(config)
        total_filtered += filter_excluded_steps(session)
        sessions.append(session)
        print()

    if total_filtered > 0:
        print(f"Excluded {total_filtered} step(s) matching keywords: {EXCLUDE_KEYWORDS}")
        print()

    print(f"Generating {OUTPUT_FILE}...")
    markdown = generate_markdown(sessions)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(markdown)

    total_completions = sum(len(s.completions) for s in sessions)
    total_raw = sum(s.total_raw_messages for s in sessions)
    print(f"Done! Wrote {len(markdown):,} characters.")
    print(f"  {total_completions} completion attempts across {len(sessions)} sessions.")
    print(f"  Extracted from {total_raw:,} raw messages.")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

