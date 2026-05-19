#!/bin/bash
echo "=== Import Status Check ==="
echo "Last 30 lines of log:"
tail -30 /app/zoho_import.log
echo ""
echo "=== File info ==="
ls -lh /app/zoho_import.log
echo ""
echo "=== Process status ==="
ps aux 2>/dev/null | grep -i zoho || echo "No zoho processes running"
