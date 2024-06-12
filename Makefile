
.PHONY: install
install: ## Install the poetry environment and install the pre-commit hooks
	@echo "🚀 Creating virtual environment using pyenv and poetry"
	@poetry install
	# @ poetry run pre-commit install
	@poetry shell

.PHONY: check
check: ## Run code quality tools.
	@echo "🚀 Checking Poetry lock file consistency with 'pyproject.toml': Running poetry --check lock"
	@poetry check --lock
	@echo "🚀 Linting code: Running ruff check --fix"
	@poetry run ruff check --fix
	@echo "🚀 Formatting code: Running ruff format"
	@poetry run ruff format
	# @echo "🚀 Static type checking: Running mypy"
	# @poetry run mypy
	# @echo "🚀 Checking for obsolete dependencies: Running deptry"
	# @poetry run deptry .

.PHONY: test
test: ## Test the code with pytest
	@echo "🚀 Testing code: Running pytest"
	@poetry run pytest tests --cov --cov-config=pyproject.toml --cov-report=xml

.PHONY: build
build: clean-build ## Build wheel file using poetry
	@echo "🚀 Creating wheel file"
	@poetry build

.PHONY: clean-build
clean-build: ## clean build artifacts
	@rm -rf dist

.PHONY: docs-test
docs-test: ## Test if documentation can be built without warnings or errors
	@poetry run sphinx-build ./docs ./docs/_build $(O)

.PHONY: docs
docs: ## Build and serve the documentation
	@poetry run sphinx-autobuild ./docs ./docs/_build $(O)

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
