QGIS_PYTHON = $(HOME)/miniforge3/envs/qgis_latest/share/qgis/python
PLUGINS_DIR = $(HOME)/.local/share/QGIS/QGIS3/profiles/default/python/plugins
PLUGIN_NAME = check_a_kea
VERSION := $(shell grep '^version=' metadata.txt | cut -d= -f2)
ZIP_NAME = $(PLUGIN_NAME)-$(VERSION).zip

test:
	pytest

test-qgis:
	PYTHONPATH=$(QGIS_PYTHON) pytest

zip:
	git archive HEAD \
	    --prefix=$(PLUGIN_NAME)/ \
	    --format=zip \
	    -o $(ZIP_NAME) \
	    -- __init__.py check_a_kea.py metadata.txt icon.png core/ i18n/
	@echo "Built $(ZIP_NAME)"

dev-install:
	ln -sfn $(CURDIR) $(PLUGINS_DIR)/$(PLUGIN_NAME)
	@echo "Symlinked $(PLUGINS_DIR)/$(PLUGIN_NAME) -> $(CURDIR)"

dev-uninstall:
	rm -f $(PLUGINS_DIR)/$(PLUGIN_NAME)
	@echo "Removed $(PLUGINS_DIR)/$(PLUGIN_NAME)"
