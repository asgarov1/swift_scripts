PYTHON := venv/bin/python3
SCRIPT := make_icon.py
INPUT ?= $(firstword $(wildcard input_flag.jpeg input_flag.jpg input_flag.png))

# Everything after `start` is treated as one comma-separated text specification.
TEXT_SPECS := $(filter-out start,$(MAKECMDGOALS))
CSV_GOALS_ARG := $(if $(strip $(TEXT_SPECS)),--csv-goals '$(TEXT_SPECS)',)

.PHONY: start help

start:
	@test -x "$(PYTHON)" || { echo "Missing virtual environment: $(PYTHON)"; exit 1; }
	@test -n "$(INPUT)" || { echo "Missing input image: add input_flag.jpeg, input_flag.jpg, or input_flag.png"; exit 1; }
	@. venv/bin/activate && python "$(SCRIPT)" --input "$(INPUT)" $(CSV_GOALS_ARG)

help:
	@echo "Usage: make start [INPUT=image] [text,x,y,font,font_size,color,anchor,weight,angle ...]"
	@echo "Example: make start"
	@echo 'Example: make start "Italian A1",695,320,,50,white,,5'
	@echo "Example: make start B1,550,520,,440,#052D12,,9,20 francais,530,730,,440,#052D12,,3,-12"

# Prevent comma-separated specifications from being treated as missing Make targets.
%:
	@:
