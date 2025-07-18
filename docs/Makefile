# Minimal makefile for Sphinx documentation

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Adjust this to point to your Python package directory (relative to this Makefile)
APIDOCSRC     = ../poly_lithic
APIDOCOUT     = $(SOURCEDIR)/api

.PHONY: help Makefile apidoc

# Default target: "make" is like "make help"
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Autogenerate .rst files from Python source using sphinx-apidoc
apidoc:
	sphinx-apidoc -o $(APIDOCOUT) $(APIDOCSRC) --force --no-toc --separate

# Build HTML docs, running apidoc first
html: apidoc
	@$(SPHINXBUILD) -M html "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

# Catch-all target: route all unknown targets to Sphinx
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
