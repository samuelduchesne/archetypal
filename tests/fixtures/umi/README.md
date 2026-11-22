# UMI sample libraries

The three UMI template libraries the project has, copied byte for byte from
`tests/input_data/umi_samples/` of archetypal v2 (branch `main`, commit `4c13297f`, the v2
line). They are the real libraries of the UMI test set (spec 003, research R18); the
hand-made edge cases are in [`edge/`](edge/README.md).

| File | Short name | Origin | Dialect (research R2) | SHA-256 |
|---|---|---|---|---|
| `BostonTemplateLibrary_2.json` | B2 | `tests/input_data/umi_samples/BostonTemplateLibrary_2.json` | Current Core JSON, pre-2023 fields (no `AdvancedModel`, `UseAdvancedModel` or hot-water `FuelType`) | `99779e8ff262cbe66adf1b7822a2a312145e221a6ed6543185f63a1157b8bbb6` |
| `BostonTemplateLibrary_nodup.json` | ND | `tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json` | Current Core JSON, pre-2023 fields | `41f6e16cf26c5977bf2b832b17c15637a20c1934aa314c896db3ea47c8dd9709` |
| `umi_samples_BostonTemplateLibrary.json` | UZ | `BostonTemplateLibrary.json` inside `tests/input_data/umi_samples/umi_samples.umi` (a zip; member dated 2017-01-09; the `.umi` file's SHA-256 is `b6a5333a3d8868bd537c253fb1bffd3a90bd52b77a48d30597e322a5fb521158`) | Archsim-era JSON (`GasType`, `Life`, `Comment` on materials) | `ed0c9b56fcb2f24869a692b0ba874a499887ff1d24c2c65d922a7a081b2bdc8d` |

The files are kept exactly as found: UZ has Windows line ends and no final newline. The
pre-commit hooks exclude them (`.pre-commit-config.yaml`) so that no formatter rewrites them.

What Basilisk at commit `5cce24e8` makes of them (`tools/basilisk-check --report`): all three
pass the harness's four checks. B2 and UZ each hold 29 components that no building template
uses; ND holds none.

Check a hash with `sha256sum tests/fixtures/umi/*.json`.
