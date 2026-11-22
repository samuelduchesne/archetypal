# Contract: the documentation site

The site every v3 spec adds pages to (FR-022–FR-025, research R5). Pages are written with
`/project-kit:diataxis`.

## Sections

| Section | Folder | Title style |
|---|---|---|
| Tutorials | `docs/tutorials/` | What the learner ends up with: "Your first UMI library". |
| How-to guides | `docs/how-to/` | "How to …". |
| Reference | `docs/reference/` | The name of the thing in the code. |
| Explanation | `docs/explanation/` | "About …", or a *why* question. |

A section appears when its first page is added; no empty section is scaffolded. Each section
folder has an `index.md` listing its pages (`navigation.indexes`).

## Page rules (checked on every change)

1. **One kind.** Front matter `diataxis:` with exactly one of `tutorial`, `how-to`,
   `reference`, `explanation`, matching the page's folder. `docs/index.md` is tagged
   `explanation` (SC-008).
2. **Examples run.** Every `python` block runs under `pytest-markdown-docs`; every `console`
   block's `$ archetypal …` lines run in a temporary folder holding the example files.
   Output shown in a page is the output the code gives (FR-024, SC-004).
3. **Reference is generated.** The Python API from docstrings (mkdocstrings), the command line
   from click (`mkdocs-click`), report fields from their JSON Schemas (spec 002), the removed
   names from `REMOVED` (R7). No hand-written table mirrors code.
4. **Same pull request.** A change to public behaviour changes its pages in the same pull
   request (constitution VI, C-09).
5. **Builds clean.** `mkdocs build -s` passes (no warnings).

## Hosting

- v3: GitHub Pages, deployed on every published release and milestone pre-release (R2).
- v2: Read the Docs, from `v2.x` (FR-025). Both sites link to each other.
