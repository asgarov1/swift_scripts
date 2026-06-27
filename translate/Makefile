SHELL := /bin/bash
.DEFAULT_GOAL := start

PYTHON := python3
SCRIPT := translate_localizations.py
ARGS ?=

path_to_folder := $(word 2,$(MAKECMDGOALS))
source_lang := $(word 3,$(MAKECMDGOALS))

.PHONY: start help

start:
	@if [[ "$(words $(MAKECMDGOALS))" -ne 3 ]]; then echo "Usage: make start <path_to_folder> <source_language> [ARGS='--dry-run']"; exit 1; fi
	@if [[ ! -d "$(path_to_folder)" ]]; then echo "Error: input folder does not exist: $(path_to_folder)"; exit 1; fi
	@$(PYTHON) "$(SCRIPT)" --source-lang "$(source_lang)" $(ARGS) "$(path_to_folder)"

help:
	@echo "Usage: make start <path_to_folder> <source_language> [ARGS='--dry-run']"
	@echo "Example: make start ../../french-b2/french-b2 fr"
	@echo "Example: make start ../../spanish-b1/spanish-b1 es ARGS='--overwrite'"

# Treat positional arguments as values rather than Make targets.
%:
	@:
