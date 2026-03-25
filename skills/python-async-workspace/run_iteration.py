#!/usr/bin/env python3
"""
Ad-hoc runner for python-async skill evals iteration-7.

Creates directory structure, runs evals via opencode CLI, and processes
events.jsonl into standard workspace artifacts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "skills" / "python-async"
EVALS_PATH = SKILL_ROOT / "evals" / "evals.json"
MODEL = "github-copilot/gpt-5.4"


def load_evals() -> list[dict]:
    payload = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
    return payload["evals"]


def create_iteration_dir(workspace: Path, iteration: str) -> Path:
    iteration_dir = workspace / iteration
    iteration_dir.mkdir(parents=True, exist_ok=True)
    return iteration_dir


def write_eval_metadata(eval_dir: Path, eval_item: dict) -> None:
    metadata = {
        "eval_id": eval_item["id"],
        "eval_name": f"eval-{eval_item['id']}",
        "prompt": eval_item["prompt"],
        "assertions": eval_item["expectations"],
    }
    (eval_dir / "eval_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def run_single_eval(
    eval_item: dict,
    config: str,
    run_dir: Path,
    skill_source: Path | None,
) -> bool:
    with tempfile.TemporaryDirectory(prefix=f"python-async-{config}-") as tmpdir:
        work_dir = Path(tmpdir)

        if skill_source and config == "with_skill":
            target = work_dir / ".opencode" / "skills" / "python-async"
            shutil.copytree(skill_source, target)

        events_path = run_dir / "events.jsonl"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "outputs").mkdir(parents=True, exist_ok=True)

        cmd = [
            "opencode",
            "run",
            "--format",
            "json",
            "--model",
            MODEL,
            eval_item["prompt"],
        ]

        start_ts = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            elapsed = time.time() - start_ts
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT for eval-{eval_item['id']} {config}")
            return False

        raw_output = proc.stdout
        events_path.write_text(raw_output, encoding="utf-8")

        process_events(
            events_path, run_dir, eval_item, config, elapsed, proc.returncode
        )
        return True


def process_events(
    events_path: Path,
    run_dir: Path,
    eval_item: dict,
    config: str,
    elapsed: float,
    return_code: int,
) -> None:
    events: list[dict] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    response_text = ""
    tool_calls: dict[str, int] = {}
    total_tool_calls = 0
    total_steps = 0
    total_tokens = 0
    event_summary_lines: list[str] = []
    skill_triggered = False
    first_ts = None
    last_ts = None

    for evt in events:
        ts = evt.get("timestamp")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        evt_type = evt.get("type", "")
        part = evt.get("part", {})

        if evt_type == "text":
            response_text += part.get("text", "")

        elif evt_type == "tool_use":
            tool_name = part.get("tool", "unknown")
            tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1
            total_tool_calls += 1
            event_summary_lines.append(f"- Tool use: {tool_name}")

            if tool_name == "skill":
                state = part.get("state", {})
                inp = state.get("input", {})
                if inp.get("name") == "python-async":
                    skill_triggered = True
                skill_name = inp.get("name", "unknown")
                event_summary_lines[-1] = f"- Tool use: skill:{skill_name}"

        elif evt_type == "step_finish":
            total_steps += 1
            reason = part.get("reason", "unknown")
            event_summary_lines.append(f"- Step finished: {reason}")
            tokens = part.get("tokens", {})
            total_tokens += tokens.get("total", 0)

        elif evt_type == "step_start":
            pass

    duration_ms = int(elapsed * 1000)
    if first_ts and last_ts:
        duration_ms = last_ts - first_ts

    duration_seconds = round(duration_ms / 1000, 3)

    outputs_dir = run_dir / "outputs"

    (outputs_dir / "response.md").write_text(response_text, encoding="utf-8")

    event_summary = "\n".join(event_summary_lines)
    transcript = (
        f"# Execution Transcript\n\n"
        f"## Eval Prompt\n\n{eval_item['prompt']}\n\n"
        f"## Configuration\n\n"
        f"- Mode: {config}\n"
        f"- Skill expected: {config == 'with_skill'}\n"
        f"- Model: {MODEL}\n\n"
        f"## Event Summary\n\n{event_summary}\n\n"
        f"## Skill Trigger Check\n\n"
        f"- python-async skill triggered: {skill_triggered}\n\n"
        f"## Final Response\n\n{response_text}\n"
    )
    (outputs_dir / "transcript.md").write_text(transcript, encoding="utf-8")

    metrics = {
        "tool_calls": tool_calls,
        "total_tool_calls": total_tool_calls,
        "total_steps": total_steps,
        "files_created": ["response.md", "transcript.md", "metrics.json"],
        "errors_encountered": 0,
        "output_chars": len(response_text),
        "transcript_chars": len(transcript),
        "skill_triggered": skill_triggered,
        "return_code": return_code,
    }
    (outputs_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    timing = {
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "total_duration_seconds": duration_seconds,
    }
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2), encoding="utf-8")


def main() -> int:
    workspace = REPO_ROOT / "skills" / "python-async-workspace"
    iteration = sys.argv[1] if len(sys.argv) > 1 else "iteration-7"

    evals = load_evals()
    iteration_dir = create_iteration_dir(workspace, iteration)

    configs = ["with_skill", "without_skill"]

    for eval_item in evals:
        eval_id = eval_item["id"]
        eval_dir = iteration_dir / f"eval-{eval_id}"
        eval_dir.mkdir(parents=True, exist_ok=True)
        write_eval_metadata(eval_dir, eval_item)

    total_runs = len(evals) * len(configs)
    completed = 0

    for config in configs:
        for eval_item in evals:
            eval_id = eval_item["id"]
            run_dir = iteration_dir / f"eval-{eval_id}" / config / "run-1"
            completed += 1
            print(f"[{completed}/{total_runs}] Running eval-{eval_id} {config}...")

            skill_source = SKILL_ROOT if config == "with_skill" else None
            ok = run_single_eval(eval_item, config, run_dir, skill_source)
            if ok:
                print(f"  eval-{eval_id} {config} done")
            else:
                print(f"  eval-{eval_id} {config} FAILED")

    print(f"\nAll runs complete. Results in {iteration_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
