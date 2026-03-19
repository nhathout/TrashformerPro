#!/usr/bin/env bash
set -euo pipefail

OUTDIR="runtime/captures"
mkdir -p "$OUTDIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTFILE="$OUTDIR/test_${TIMESTAMP}.jpg"

echo "Listing cameras..."
rpicam-hello --list-cameras

echo "Capturing test image to $OUTFILE ..."
rpicam-still --nopreview -o "$OUTFILE"

echo "Saved: $OUTFILE"