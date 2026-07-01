#!/bin/bash

set -e

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 <project_path> <language> [output_dir]"
  exit 1
fi

PROJECT_PATH="$1"
LANGUAGE="$2"
OUTPUT_DIR="${3:-output}"

if [ ! -d "$PROJECT_PATH" ]; then
  echo "Error: Directory does not exist: $PROJECT_PATH"
  exit 1
fi

# delete old stuff before generating new
rm -f input.txt
mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_DIR"/*.mp3

python3 collect_foreign.py "$PROJECT_PATH"
python3 generate_audio_clips.py --lang "$LANGUAGE" --out "$OUTPUT_DIR"
