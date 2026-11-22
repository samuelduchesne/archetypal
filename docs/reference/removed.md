---
diataxis: reference
---

# Removed v2 capabilities

Every public name, module, command and option of archetypal 2.18 that archetypal 3 does not
provide, with its replacement or the reason it has none. The tables are generated from
`archetypal._removed.REMOVED`, the table the migration errors are raised from.

Importing a removed name or module raises `RemovedInArchetypal3Error`, an `ImportError` whose
message gives the replacement and links to the row in
[How to migrate from archetypal 2](../how-to/migrate-from-v2.md). The `archetypal` command
rejects a removed command or option with exit status 2, before doing any work.

<!-- removed-capabilities -->
