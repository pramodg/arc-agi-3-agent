# Everyday commands for the ARC-AGI-3 agent. `make` alone lists them.
# Everything Python runs on the one shared 3.12 environment that
# pipeline/toolchain.py builds (docs/setup.md).

RUN    := python3 -m pipeline.toolchain run
GAME   ?=
STEPS  ?= 200
# The Kaggle CLI from the shared environment, given the token in
# .kaggle/access_token through the one variable it reads for token auth.
TOKEN  := .kaggle/access_token
KAGGLE  = KAGGLE_API_TOKEN=$$(cat $(TOKEN)) \
          $$(python3 -m pipeline.toolchain python | xargs dirname)/kaggle
KERNEL  = $$(python3 -c 'import json; print(json.load(open("notebooks/kernel-metadata.json"))["id"])')

.DEFAULT_GOAL := help
.PHONY: help setup play-local play-random games test notebook submit status clean token

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | \
	    sed -E 's/^([a-z-]+):.*## (.*)/  \1|\2/' | column -t -s '|'
	@echo "  variables: GAME=$(GAME) STEPS=$(STEPS)"

setup: ## Build or reuse the 3.12 environment and link vendor/
	python3 -m pipeline.toolchain ensure

play-local: ## Play agent/my_agent.py on every public game, or GAME=a,b
	$(RUN) scripts/play_local.py $(if $(GAME),--game $(GAME)) --max-steps $(STEPS)

play-random: ## The random agent at its committed cap (scripts/random_agent.py)
	$(RUN) scripts/play_local.py --agent scripts/random_agent.py \
	    $(if $(GAME),--game $(GAME)) \
	    $(if $(filter command line,$(origin STEPS)),--max-steps $(STEPS))

games: ## List the public games
	$(RUN) scripts/play_local.py --list

test: ## Run the unit tests
	$(RUN) -m unittest discover -s tests

notebook: ## Build notebooks/submission.ipynb from agent/my_agent.py
	$(RUN) scripts/build_notebook.py

token:
	@test -s $(TOKEN) || { echo "No Kaggle token at $(TOKEN)."; \
	    echo "Create one at https://www.kaggle.com/settings (API, Create New Token)"; \
	    echo "and save it there as a single line."; exit 1; }

submit: notebook token ## Build the notebook and push it to Kaggle
	@! grep -q REPLACE_WITH_YOUR_USERNAME notebooks/kernel-metadata.json || { \
	    echo "Put your Kaggle user name in notebooks/kernel-metadata.json first."; \
	    exit 1; }
	$(KAGGLE) kernels push -p notebooks/
	@echo "Pushed. Follow the run with: make status"

status: token ## Status of the latest run of the Kaggle notebook
	@$(KAGGLE) kernels status $(KERNEL)

clean: ## Remove generated files in this checkout (the shared env stays)
	rm -rf vendor recordings notebooks/submission.ipynb __pycache__
