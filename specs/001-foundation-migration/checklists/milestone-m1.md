# Milestone M1 checklist: archetypal 3 foundation

**Purpose**: Record the evidence for M1's success criteria as each is checked
**Feature**: [spec.md](../spec.md)

## SC-002: install size and duplicates

- [x] archetypal 3 installs fewer packages than archetypal 2 on the same Python version.
  - Date: 2026-11-22
  - Command: `uv run python verification/install_size.py` (`uv pip compile`, Python 3.12, uv
    0.11.32)
  - archetypal 2.18.10 (last v2 release; 2.18.11 does not exist): **109 packages**
  - archetypal 3 (this checkout, epinterface from the fork at `dee8d343` via
    `[tool.uv.sources]`): **25 packages**
  - Both counts include archetypal itself. Result: PASS.
- [x] The archetypal 3 resolution contains none of `eppy`, `geomeppy`, `esoreader`,
  `energy_pandas`, `pyclipper`, `pypoly2tri`, `transforms3d` or `shapely`; the archetypal 2
  resolution contains `eppy`, `esoreader`, `energy-pandas`, `pyclipper`, `pypoly2tri`,
  `transforms3d` and `shapely`.

archetypal 3's resolution (2026-11-22): annotated-types, anyio, archetypal, certifi, click,
epinterface, h11, httpcore, httpx, idfkit, idna, networkx, numpy, pandas, pydantic,
pydantic-core, pydantic-settings, python-dateutil, python-dotenv, pytz, pyyaml, tqdm,
typing-extensions, typing-inspection, tzdata.

Because v3's count is smaller, no UP-4 note was needed for SC-002.
