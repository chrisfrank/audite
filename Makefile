###############################################################################
# PYTHON BOILERPLATE
###############################################################################
PACKAGE_NAME := audite

# Declare a venv-aware python alias
VIRTUAL_ENV := $(shell pwd)/venv
PYTHON := $(VIRTUAL_ENV)/bin/python3

# Installation artifacts
INSTALLED := $(VIRTUAL_ENV)/.installed_$(PACKAGE_NAME)
PRECOMMIT := .git/hooks/pre-commit

.PHONY: install
install: $(INSTALLED)

# Runs linters and tests before each commit
# run `git commit --no-verify` to skip
$(PRECOMMIT):
	@echo "*** installing git hooks ***"
	@rm -f .git/hooks/pre-commit;
	@printf "#!/bin/sh\nBLACK_ARGS=--check ISORT_ARGS=--check-only make lint || exit 1\nmake test || exit 1" > .git/hooks/pre-commit && \
	chmod +x .git/hooks/pre-commit ; \

# Creates a python virtual environment
$(VIRTUAL_ENV): $(PRECOMMIT)
	@test -d $(VIRTUAL_ENV) || python3 -m venv $(VIRTUAL_ENV)

# Installs/upgrades dependencies when the manifests change
$(INSTALLED): $(VIRTUAL_ENV) requirements.txt requirements.dev.txt
	@echo "*** installing dependencies ***"
	@$(PYTHON) -m pip install --upgrade pip setuptools wheel || exit 1
	@$(PYTHON) -m pip install -r requirements.dev.txt || exit 1
	@touch $(INSTALLED)

.PHONY: lint
lint: install
	@echo "*** isort ***"
	@$(PYTHON) -m isort $(ISORT_ARGS) --profile black $(PACKAGE_NAME) || exit 1
	@echo "*** black ***"
	@$(PYTHON) -m black $(BLACK_ARGS) $(PACKAGE_NAME) || exit 1
	@echo "*** flake8 ***"
	@$(PYTHON) -m flake8 $(PACKAGE_NAME) --max-line-length=88 || exit 1
	@echo "*** mypy ***"
	@$(PYTHON) -m mypy --strict $(PACKAGE_NAME)

.PHONY: test
test: install
	$(PYTHON) -m pytest -s $(PACKAGE_NAME)

###############################################################################
# END BOILERPLATE
###############################################################################
.PHONY: run
run: install
	@$(PYTHON) -m audite

.PHONY: clean
clean:
	@echo "*** cleaning ***"
	@rm -rf $(VIRTUAL_ENV) $(PRECOMMIT) \
		*.egg-info .mypy_cache .pytest_cache
