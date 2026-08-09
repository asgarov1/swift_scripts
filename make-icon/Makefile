PYTHON := venv/bin/python3
SCRIPT := make_icon.py
INPUT ?= $(firstword $(wildcard input.png input.jpg input.jpeg input_flag.png input_flag.jpg input_flag.jpeg))

# Everything after `start` is treated as one comma-separated text specification.
TEXT_SPECS := $(filter-out start,$(MAKECMDGOALS))
CSV_GOALS_ARG := $(if $(strip $(TEXT_SPECS)),--csv-goals '$(TEXT_SPECS)',)

.PHONY: start help

start:
	@test -x "$(PYTHON)" || { echo "Missing virtual environment: $(PYTHON)"; exit 1; }
	@test -n "$(INPUT)" || { echo "Missing input image: add input.png, input.jpg, or input.jpeg"; exit 1; }
	@. venv/bin/activate && python "$(SCRIPT)" --input "$(INPUT)" $(CSV_GOALS_ARG)

help:
	@echo "Usage: make start [INPUT=image] [text,x,y,font,font_size,color,anchor,weight,angle,opacity ...]"
	@echo "Example: make start"
	@echo 'Example: make start "Italian A1",695,320,,50,white,,5'
	@echo "Example: make start B1,550,520,,440,#052D12,,9,20,0.5 francais,530,730,,440,#052D12,,3,-12,0.8"

# Prevent comma-separated specifications from being treated as missing Make targets.
%:
	@:
