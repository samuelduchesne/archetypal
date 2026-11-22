---
diataxis: how-to
---

# How to install archetypal 3

archetypal 3 runs on Python 3.10, 3.11 and 3.12, on Linux, macOS and Windows. Until v3.0.0 is
released on PyPI, you install it from its git repository, at a milestone tag such as
`v3.0.0a1`, together with the fork of epinterface it depends on. This guide gives the commands
for both stages.

## Check your Python version

```console
$ python --version
```

Any 3.10, 3.11 or 3.12 release works. On Python 3.13 or later, and on 3.9 or earlier, pip
refuses to install archetypal 3 and names the supported range (`>=3.10,<3.13`); create the
environment with a supported Python instead.

## Install from git, before v3.0.0

archetypal 3 needs SBEM changes that the epinterface releases on PyPI do not have yet, and those
releases require archetypal 2. archetypal therefore depends on a maintained fork of
epinterface, which is not on PyPI either: install both from git, in a new environment, so that
an existing archetypal 2 environment keeps working.

1. Pick the milestone tag to install from the
   [releases page](https://github.com/samuelduchesne/archetypal/releases).
2. Find the epinterface revision that tag uses: it is the `rev` (or `tag`) of `epinterface`
   under `[tool.uv.sources]` in archetypal's `pyproject.toml` at that tag.
3. Install both in one command, so that pip takes epinterface from the fork rather than from
   PyPI:

   ```console
   $ python -m venv .venv
   $ source .venv/bin/activate
   $ pip install "epinterface @ git+https://github.com/samuelduchesne/epinterface@REVISION" "archetypal @ git+https://github.com/samuelduchesne/archetypal@TAG"
   ```

   Replace `REVISION` and `TAG` with the values from steps 1 and 2. On Windows, activate the
   environment with `.venv\Scripts\activate` instead.

If pip reports that epinterface requires `archetypal==2.18.10`, it took epinterface from PyPI:
the fork's URL was missing from the command. Run the command again with both requirements.

Working on archetypal itself is different: `uv sync` in a clone reads `[tool.uv.sources]` and
installs the fork by itself.

## Install from PyPI, from v3.0.0

Once v3.0.0 is released, install it like any package:

```console
$ pip install archetypal
```

To keep archetypal 2 instead, pin it: `pip install "archetypal<3"`.

## Check the installation

```console
$ python -c "import archetypal; print(archetypal.__version__)"
```

It prints the version you installed. Importing archetypal creates no file or folder and reads
no environment variable. To move scripts written for archetypal 2, continue with
[How to migrate from archetypal 2](migrate-from-v2.md).
