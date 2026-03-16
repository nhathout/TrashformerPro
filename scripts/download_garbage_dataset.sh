#!/usr/bin/env bash
set -euo pipefail

DATASET="sumn2u/garbage-classification-v2"
OUTDIR="data/raw/garbage_v2"

mkdir -p "$OUTDIR"

kaggle datasets download -d "$DATASET" -p "$OUTDIR" --unzip

echo "Downloaded and extracted $DATASET to $OUTDIR"