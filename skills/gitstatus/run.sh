#!/bin/bash
# Git Status Skill — shows repo status and recent activity

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    echo "Not inside a git repository."
    exit 1
fi

echo "═══════════════════════════════════════"
echo "  GIT STATUS"
echo "═══════════════════════════════════════"
echo ""
echo "  Branch:      $(git branch --show-current 2>/dev/null)"
echo "  Remote:      $(git remote get-url origin 2>/dev/null || echo 'none')"
echo ""
echo "  Status:"
git status --short 2>/dev/null | head -20 | while read line; do
    echo "    $line"
done
echo ""
echo "  Recent commits:"
git log --oneline -5 2>/dev/null | while read line; do
    echo "    $line"
done
echo ""
echo "═══════════════════════════════════════"
