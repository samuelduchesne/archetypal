.PHONY: install
install: ## Install the virtual environment and install the pre-commit hooks
	@if [ ! -d .git ]; then \
		echo "❌ Error: Not a git repository. Run 'git init -b main' first (see README step 1)."; \
		exit 1; \
	fi
	@echo "🚀 Creating virtual environment using uv"
	@uv sync
	@uv run pre-commit install

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking lock file consistency with 'pyproject.toml'"
	@uv lock --locked
	@echo "🚀 Linting code: Running pre-commit"
	@uv run pre-commit run -a
	@echo "🚀 Static type checking: Running pyright"
	@uv run pyright
	@echo "🚀 Checking idfkit use across EnergyPlus releases: Running idfkit check"
	@uv run idfkit check
	@echo "🚀 Checking for obsolete dependencies: Running deptry"
	@uv run deptry src
	@$(MAKE) --no-print-directory basilisk-fields
	@echo "🚀 Checking documentation: building the site in strict mode"
	@uv run mkdocs build -s
	@echo "🚀 Checking documentation: Diátaxis tags"
	@uv run pytest tests/unit/test_docs_tags.py

.PHONY: basilisk-fields
basilisk-fields: ## Compare Basilisk's serialised fields with tests/data/basilisk_fields.json (needs dotnet)
	@echo "🚀 Checking the UMI field list against the pinned Basilisk"
	@if ! command -v dotnet >/dev/null 2>&1; then \
		echo "dotnet not installed: skipped (CI always runs this check)"; \
	elif [ ! -f tools/basilisk-check/basilisk-check.csproj ] || [ ! -f tests/data/basilisk_fields.json ]; then \
		echo "tools/basilisk-check or tests/data/basilisk_fields.json not written yet: skipped"; \
	else \
		tools/basilisk-check/fetch-basilisk.sh && \
		dotnet build tools/basilisk-check --nologo -v q && \
		dotnet run --no-build --project tools/basilisk-check -- --list-fields | diff - tests/data/basilisk_fields.json; \
	fi

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@uv run python -m pytest --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: build
build: clean-build ## Build wheel file
	@echo "🚀 Creating wheel file"
	@uvx --from build pyproject-build --installer uv

.PHONY: clean-build
clean-build: ## Clean build artifacts
	@echo "🚀 Removing build artifacts"
	@uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

.PHONY: publish
publish: ## Publish a release to PyPI.
	@echo "🚀 Publishing."
	@uvx twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

.PHONY: build-and-publish
build-and-publish: build publish ## Build and publish.

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@uv run mkdocs build -s

.PHONY: docs
docs: ## Build and serve the documentation
	@uv run mkdocs serve

.PHONY: help
help:
	@uv run python -c "import re; \
	[[print(f'\033[36m{m[0]:<20}\033[0m {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(makefile).read(), re.M)] for makefile in ('$(MAKEFILE_LIST)').strip().split()]"

.DEFAULT_GOAL := help
