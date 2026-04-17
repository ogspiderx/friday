#!/bin/bash
# Disk Usage Skill — shows disk space info

echo "═══════════════════════════════════════"
echo "  DISK USAGE"
echo "═══════════════════════════════════════"
echo ""
echo "  System partitions:"
df -h --output=source,size,used,avail,pcent,target 2>/dev/null | grep -v tmpfs | head -10 | while read line; do
    echo "    $line"
done
echo ""
echo "  Current directory ($(pwd)):"
echo "    Total: $(du -sh . 2>/dev/null | cut -f1)"
echo ""
echo "  Largest items:"
du -sh ./* 2>/dev/null | sort -rh | head -10 | while read line; do
    echo "    $line"
done
echo ""
echo "═══════════════════════════════════════"
