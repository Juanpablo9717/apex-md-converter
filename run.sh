#!/usr/bin/env bash
# Full pipeline: PDF -> out/final.md + every verification layer. Usage:
#   APEX_PDF=/path/APEX_Message_Reference_<release>.pdf APEX_WORK=/path/work ./run.sh
set -euo pipefail
cd "$(dirname "$0")"
: "${APEX_PDF:?set APEX_PDF to the PDF}"; export APEX_WORK="${APEX_WORK:-$PWD/work}"
PY="${PYTHON:-./venv/bin/python}"
[ -x "$PY" ] || { python3 -m venv venv && ./venv/bin/pip install -q -r requirements.txt; PY=./venv/bin/python; }
command -v pdftotext >/dev/null || { echo "poppler is required: brew install poppler"; exit 1; }
mkdir -p "$APEX_WORK/out" "$APEX_WORK/ref" "$APEX_WORK/ocr"

echo "== images";     $PY images.py ${APEX_REUSE:+--reuse "$APEX_REUSE"} || { echo "transcribe the images listed above (RUNBOOK.md, step 3), then re-run"; exit 1; }
echo "== convert";    $PY hidden.py && $PY convert.py
echo "== assemble";   $PY assemble.py >/dev/null
echo "== references (poppler)"
pdftotext -raw -x 0 -y 57 -W 612 -H 639 "$APEX_PDF" "$APEX_WORK/ref/body.txt"
pdftohtml -xml -i -q -fontfullname -hidden "$APEX_PDF" "$APEX_WORK/ref/pdf" >/dev/null
echo "== checks"
$PY checks/verify.py >/dev/null
$PY checks/check_structure.py >/dev/null
$PY checks/check_codeblocks.py >/dev/null || true
$PY checks/check_rows.py "$APEX_WORK/ref/pdf.xml" "$APEX_WORK/out/final.md" >/dev/null
$PY checks/check_cells.py "$APEX_WORK/ref/pdf.xml" "$APEX_WORK/out/final.md" >/dev/null
$PY checks/check_errors.py "$APEX_WORK/ref/pdf.xml" "$APEX_WORK/out/final.md" | tee "$APEX_WORK/out/errors_report.txt"
echo "== verdict";    $PY gate.py
echo "Output: $APEX_WORK/out/final.md"
