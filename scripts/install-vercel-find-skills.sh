#!/usr/bin/env bash
# Installs the Vercel "find-skills" package into Cursor via npx (run outside Friday).
set -euo pipefail
exec npx skills add https://github.com/vercel-labs/skills --skill find-skills
