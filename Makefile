# Run tests across multiple Python versions using `uv` persistent venvs.
#
# Usage:
#   make create-venvs   # create persistent venvs with uv
#   make install        # install project and test deps into each venv
#   make testall        # run pytest in each venv
#   make clean-venvs    # remove created venv directories

PYTHONS := 3.10 3.11 3.12 3.13
VENV_PREFIX := .venv-
CC ?= gcc
export CC

.PHONY: create-venvs install install-% testall test-% clean-venvs

create-venv-%: # usage: make create-venv-3.10
	uv venv $(VENV_PREFIX)$(subst create-venv-,,$@) --python=$(subst create-venv-,,$@)

create-venvs:
	@for py in $(PYTHONS); do \
		uv venv $(VENV_PREFIX)$$py --python=$$py; \
	done

installall: # install project and test deps into each venv
	@for py in $(PYTHONS); do \
		. $(VENV_PREFIX)$$py/bin/activate; \
		uv pip install -e .[dev]; \
		deactivate; \
	done

install-%: # usage: make install-3.10
	. $(VENV_PREFIX)$(subst install-,,$@)/bin/activate; \
	uv pip install -e .[dev]; \
	deactivate

testall: # run pytest in each venv
	@for py in $(PYTHONS); do \
		. $(VENV_PREFIX)$$py/bin/activate; \
		pytest --tb=short tests; \
		deactivate; \
	done

test-%: # usage: make test-3.10
	. $(VENV_PREFIX)$(subst test-,,$@)/bin/activate; \
	pytest --tb=short tests; \
	deactivate