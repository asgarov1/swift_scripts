PYTHON := venv/bin/python3
SCRIPT := make_icon.py
INPUT ?= $(firstword $(wildcard input_flag.jpeg input_flag.jpg input_flag.png))

# Everything after `start` is treated as one comma-separated text specification.
TEXT_SPECS := $(filter-out start,$(MAKECMDGOALS))

.PHONY: start help

start:
	@test -x "$(PYTHON)" || { echo "Missing virtual environment: $(PYTHON)"; exit 1; }
	@test -n "$(INPUT)" || { echo "Missing input image: add input_flag.jpeg, input_flag.jpg, or input_flag.png"; exit 1; }
	@. venv/bin/activate && python "$(SCRIPT)" --input "$(INPUT)" $(foreach spec,$(TEXT_SPECS),--csv '$(spec)')

help:
	@echo "Usage: make start [INPUT=image] text,x,y,font,font_size,color,anchor,weight [...]"
	@echo "Example: make start B1,550,520,,440,#052D12,,9 francais,530,730,,440,#052D12,,3"

# Prevent comma-separated specifications from being treated as missing Make targets.
%:
	@:
