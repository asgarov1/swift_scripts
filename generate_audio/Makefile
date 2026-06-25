SHELL := /bin/bash
.DEFAULT_GOAL := start

.PHONY: start

path_to_folder := $(word 2,$(MAKECMDGOALS))
lang := $(word 3,$(MAKECMDGOALS))

start:
	@if [[ "$(words $(MAKECMDGOALS))" -ne 3 ]]; then echo "Usage: make start /path/to/input <language>"; exit 1; fi
	@if [[ ! -d "$(path_to_folder)" ]]; then echo "Error: input folder does not exist: $(path_to_folder)"; exit 1; fi
	@if [[ ! -f "venv/bin/activate" ]]; then echo "Error: virtual environment not found at venv/"; exit 1; fi
	@source venv/bin/activate && \
		python3 collect_foreign.py "$(path_to_folder)" && \
		python3 generate_audio_clips.py --lang "$(lang)"

# Treat the positional arguments as values rather than Make targets.
%:
	@:
