"""
skills/loader.py — Dynamic skill discovery and metadata loading.

Scans the skills/ directory for subdirectories containing:
  - skill.md   → metadata (name, description, triggers, args)
  - run.sh     → executable script

Skills are the preferred execution path over raw shell commands.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from config.settings import get_settings


@dataclass
class Skill:
    """Represents a loaded skill with its metadata."""
    name: str
    path: Path
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    has_runner: bool = False
    usage_count: int = 0
    success_rate: float = 0.0
    avg_runtime: float = 0.0

    def __repr__(self):
        return f"Skill({self.name}, triggers={self.triggers})"


def _parse_skill_md(md_path: Path) -> dict:
    """
    Parse a skill.md file for metadata.
    
    Expected format (flexible markdown):
        # Skill Name
        Description text here.
        
        ## Triggers
        - keyword1
        - keyword2
        
        ## Args
        - arg1: description
        - arg2: description
        
        ## Metrics
        - usage_count: 0
        - success_rate: 0.0
        - avg_runtime: 0.0
    """
    metadata = {
        "name": "", "description": "", "triggers": [], "args": [],
        "usage_count": 0, "success_rate": 0.0, "avg_runtime": 0.0
    }

    if not md_path.exists():
        return metadata

    content = md_path.read_text()
    lines = content.strip().split("\n")

    current_section = None

    for line in lines:
        stripped = line.strip()

        # Parse heading
        if stripped.startswith("# ") and not stripped.startswith("## "):
            metadata["name"] = stripped[2:].strip()
            current_section = "description"
            continue

        if stripped.startswith("## "):
            section_name = stripped[3:].strip().lower()
            if "trigger" in section_name:
                current_section = "triggers"
            elif "arg" in section_name:
                current_section = "args"
            elif "desc" in section_name:
                current_section = "description"
            elif "metric" in section_name:
                current_section = "metrics"
            else:
                current_section = None
            continue

        # Parse content by section
        if current_section == "description" and stripped:
            if metadata["description"]:
                metadata["description"] += " "
            metadata["description"] += stripped

        elif current_section == "triggers" and stripped.startswith("- "):
            trigger = stripped[2:].strip().lower()
            if trigger:
                metadata["triggers"].append(trigger)

        elif current_section == "args" and stripped.startswith("- "):
            arg = stripped[2:].strip()
            if arg:
                metadata["args"].append(arg.split(":")[0].strip())
                
        elif current_section == "metrics" and stripped.startswith("- "):
            parts = stripped[2:].split(":", 1)
            if len(parts) == 2:
                key, val = parts[0].strip(), parts[1].strip()
                if key == "usage_count":
                    try: metadata["usage_count"] = int(val)
                    except: pass
                elif key == "success_rate":
                    try: metadata["success_rate"] = float(val)
                    except: pass
                elif key == "avg_runtime":
                    try: metadata["avg_runtime"] = float(val.replace("s", ""))
                    except: pass

    return metadata


def load_skills() -> list[Skill]:
    """
    Scan the skills directory and load all valid skills.
    
    A valid skill has a directory with at least a skill.md.
    run.sh is optional but required for execution.
    
    Returns:
        List of Skill objects.
    """
    settings = get_settings()
    skills_dir = settings.skills_dir
    skills = []

    if not skills_dir.exists():
        return skills

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(("_", ".")):
            continue

        skill_md = entry / "skill.md"
        run_sh = entry / "run.sh"

        if not skill_md.exists():
            continue

        metadata = _parse_skill_md(skill_md)

        skill = Skill(
            name=metadata.get("name") or entry.name,
            path=entry,
            description=metadata.get("description", ""),
            triggers=metadata.get("triggers", []),
            args=metadata.get("args", []),
            has_runner=run_sh.exists(),
            usage_count=metadata.get("usage_count", 0),
            success_rate=metadata.get("success_rate", 0.0),
            avg_runtime=metadata.get("avg_runtime", 0.0),
        )

        skills.append(skill)

    return skills

def save_skill_metrics(skill: Skill):
    """Rewrite the skill.md file to update the metrics section."""
    md_path = skill.path / "skill.md"
    if not md_path.exists():
        return
        
    content = md_path.read_text()
    lines = content.split("\n")
    
    # Check if ## Metrics exists
    metrics_start = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("## Metrics"):
            metrics_start = i
            break
            
    metrics_text = (
        f"## Metrics\n"
        f"- usage_count: {skill.usage_count}\n"
        f"- success_rate: {skill.success_rate:.2f}\n"
        f"- avg_runtime: {skill.avg_runtime:.2f}s"
    )
            
    if metrics_start != -1:
        # Find end of metrics section
        metrics_end = metrics_start + 1
        while metrics_end < len(lines) and not lines[metrics_end].strip().startswith("## "):
            metrics_end += 1
            
        new_lines = lines[:metrics_start] + [metrics_text] + lines[metrics_end:]
    else:
        # Append to end
        if lines and lines[-1].strip() != "":
            lines.append("")
        new_lines = lines + [metrics_text]
        
    md_path.write_text("\n".join(new_lines))



def get_skill_names() -> list[str]:
    """Return just the names of all available skills."""
    return [s.name for s in load_skills()]
