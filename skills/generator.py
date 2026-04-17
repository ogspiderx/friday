"""
skills/generator.py — Adaptive Skill Minting.

Powered by the strong model, this module takes an intent or objective
and a sequence of successful bash commands, and writes a fully operational
new skill (skill.md metadata + run.sh script) dynamically into the
skills directory.
"""

import os
import json
from pathlib import Path
from groq import Groq
from config.settings import get_settings
from rich.console import Console

console = Console()

GENERATOR_SYSTEM_PROMPT = """You are the Skill Evolution Engine for FRIDAY.
You take an Objective and a sequence of successful Bash Commands and mint a reusable Skill.
Output exactly ONE JSON object with no prefix, no markdown block. Just the raw JSON.

Format:
{
  "skill_name": "ShortLowerCaseNoSpaces",
  "display_name": "Readable Name",
  "description": "1 sentence description of what the skill does",
  "triggers": ["list", "of", "trigger", "phrases", "without", "arguments"],
  "bash_script": "#!/bin/bash\\n# The exact hardened bash statements here\\n"
}

Rules:
- The bash_script MUST include `#!/bin/bash` at the top.
- The bash_script should safely encapsulate the user's successful commands. Provide output feedback via standard bash echoing.
- Do not output anything except the JSON."""

class SkillGenerator:
    def __init__(self):
        self._settings = get_settings()
        self.client = Groq(api_key=self._settings.groq_api_key)

    def create_skill(self, objective: str, commands: list[str]) -> bool:
        """
        Dynamically construct and write a new skill based on successful inputs.
        """
        prompt = (
            f"Objective / Initial Request: {objective}\n"
            f"Successful Command Sequence:\n"
            + "\n".join([f"  - {cmd}" for cmd in commands])
        )

        try:
            console.print(f"  [dim]🔨 Minting new skill for: {objective[:40]}...[/dim]")
            response = self.client.chat.completions.create(
                model=self._settings.get_model("reason"),
                messages=[
                    {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_completion_tokens=800,
                response_format={"type": "json_object"},
            )

            from core.budget import get_tracker
            get_tracker().record_usage(response.usage)

            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            
            # Phase 13: Validate Skill
            from skills.validator import SkillValidator
            validator = SkillValidator()
            validation = validator.validate_proposal(data)
            
            if not validation["valid"]:
                console.print(f"  [yellow]Skill Generation Rejected by Validator:[/yellow] {validation['reason']}")
                return False
            
            skill_id = data.get("skill_name", "generated_skill").lower().replace(" ", "_")
            skill_dir = self._settings.skills_dir / skill_id
            
            # Avoid overwriting existing skills explicitly
            if skill_dir.exists():
                skill_dir = self._settings.skills_dir / f"{skill_id}_auto"

            # 1. Create directory
            os.makedirs(skill_dir, exist_ok=True)
            
            # 2. Write skill.md
            md_content = (
                f"# {data.get('display_name', skill_id)}\n\n"
                f"{data.get('description', 'Auto-generated skill.')}\n\n"
                f"## Triggers\n"
            )
            for t in data.get("triggers", []):
                md_content += f"- {t}\n"
                
            with open(skill_dir / "skill.md", "w") as f:
                f.write(md_content)
                
            # 3. Write run.sh
            script_path = skill_dir / "run.sh"
            with open(script_path, "w") as f:
                f.write(data.get("bash_script", "#!/bin/bash\necho 'Error generating script.'"))
                
            # Make executable
            os.chmod(script_path, 0o755)
            
            console.print(f"  [bold green]✓ New Skill Learned:[/bold green] {data.get('display_name')}")
            return True

        except Exception as e:
            console.print(f"  [red]Failed to generate skill: {e}[/red]")
            return False
