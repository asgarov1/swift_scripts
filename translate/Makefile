SHELL := /bin/bash
.DEFAULT_GOAL := start

PYTHON := python3
SCRIPT := translate_localizations.py
APPCONFIG_SCRIPT := translate_appconfig.py
PHRASE_SCRIPT := translate_phrase.py
ARGS ?=
TARGET_LANG ?=

path_to_folder := $(word 2,$(MAKECMDGOALS))
source_lang := $(word 3,$(MAKECMDGOALS))
phrase := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
target_lang_arg := $(if $(TARGET_LANG),--target-lang "$(TARGET_LANG)",)

.PHONY: start translate translate-appconfig help FORCE

start:
	@if [[ "$(words $(MAKECMDGOALS))" -ne 3 ]]; then echo "Usage: make start <path_to_folder> <source_language> [ARGS='--dry-run']"; exit 1; fi
	@if [[ ! -d "$(path_to_folder)" ]]; then echo "Error: input folder does not exist: $(path_to_folder)"; exit 1; fi
	@$(PYTHON) "$(SCRIPT)" --source-lang "$(source_lang)" $(ARGS) "$(path_to_folder)"

translate-appconfig:
	@if [[ "$(words $(MAKECMDGOALS))" -ne 3 ]]; then echo "Usage: make translate-appconfig <path_to_swift_file_or_folder> <source_language> [ARGS='--dry-run']"; exit 1; fi
	@if [[ ! -e "$(path_to_folder)" ]]; then echo "Error: input path does not exist: $(path_to_folder)"; exit 1; fi
	@$(PYTHON) "$(APPCONFIG_SCRIPT)" --source-lang "$(source_lang)" $(ARGS) "$(path_to_folder)"

translate:
	@if [[ "$(words $(MAKECMDGOALS))" -lt 2 ]]; then echo "Usage: make translate <english word or phrase> [TARGET_LANG=<language>]"; exit 1; fi
	@$(PYTHON) "$(PHRASE_SCRIPT)" $(ARGS) $(target_lang_arg) "$(phrase)"

help:
	@echo "Usage: make start <path_to_folder> <source_language> [ARGS='--dry-run']"
	@echo "Example: make start ../../french-b2/french-b2 fr"
	@echo "Example: make start ../../spanish-b1/spanish-b1 es ARGS='--overwrite'"
	@echo "Usage: make translate <english word or phrase> [TARGET_LANG=<language>] [ARGS='--json']"
	@echo "Example: make translate good morning"
	@echo "Example: make translate good morning TARGET_LANG=italian"
	@echo "Usage: make translate-appconfig <path_to_swift_file_or_folder> <source_language> [ARGS='--dry-run']"
	@echo "Example: make translate-appconfig ../../Swedish/swedish-a2/swedish-a2 english"
	@echo "Example: make translate-appconfig ../../Swedish/swedish-a2/swedish-a2/swedish_a2App.swift en ARGS='--dry-run'"

# Treat positional arguments as values rather than Make targets.
%: FORCE
	@:

FORCE:
