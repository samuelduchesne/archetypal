# archetypal

[![Release](https://img.shields.io/github/v/release/samuelduchesne/archetypal)](https://github.com/samuelduchesne/archetypal/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/samuelduchesne/archetypal/main.yml?branch=main)](https://github.com/samuelduchesne/archetypal/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/samuelduchesne/archetypal/branch/main/graph/badge.svg)](https://codecov.io/gh/samuelduchesne/archetypal)
[![License](https://img.shields.io/github/license/samuelduchesne/archetypal)](https://github.com/samuelduchesne/archetypal/blob/main/LICENSE)

Create, translate and codify building energy archetypes on SBEM.

**[Documentation](https://samuelduchesne.github.io/archetypal/)** | **[GitHub](https://github.com/samuelduchesne/archetypal/)**

## Installation

```bash
pip install archetypal
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add archetypal
```

## Usage

```python
import archetypal

# TODO: Add usage examples
```

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

### Setup

```bash
# Clone the repository
git clone https://github.com/samuelduchesne/archetypal.git
cd archetypal

# Install dependencies and pre-commit hooks
make install
```

> **Note:** Run `git init -b main` first if you're starting from a cookiecutter template.

### Commands

```bash
make install    # Install dependencies and pre-commit hooks
make check      # Run linting, formatting, and type checks
make test       # Run tests with coverage
make docs       # Serve documentation locally
make docs-test  # Test documentation build
```

### First-time setup for new projects

If you just created this project from the cookiecutter template:

1. Create a GitHub repository with the same name
2. Install dependencies, which creates `uv.lock`, then commit and push. CI needs the lock file.

   ```bash
   git init -b main
   make install
   git add .
   git commit -m "Initial commit"
   git remote add origin git@github.com:samuelduchesne/archetypal.git
   git push -u origin main
   ```

For detailed setup instructions, see the [project-kit-cookiecutter tutorial](https://samuelduchesne.github.io/project-kit-cookiecutter/tutorial/).


## Releasing

1. Bump the version: `uv version --bump <major|minor|patch>`
2. Commit and push
3. Create a [new release](https://github.com/samuelduchesne/archetypal/releases/new) on GitHub with a tag matching the version (e.g., `1.0.0`)

The GitHub Action will automatically publish to PyPI. See the [publishing guide](https://samuelduchesne.github.io/project-kit-cookiecutter/features/publishing/) for initial setup.

> **First release?** After the workflow completes, enable GitHub Pages: go to `Settings > Pages` and select the `gh-pages` branch.


## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

*Built with [project-kit-cookiecutter](https://github.com/samuelduchesne/project-kit-cookiecutter)*
