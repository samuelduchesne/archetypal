"""The audit of SC-006 (spec 003, research R16): no loss goes unreported.

Shared by `tests/unit/umi/test_audit.py` (the UMI test set) and
`tests/reference/test_umi_round_trip.py` (spec 002's reference buildings).

- `audit_library(path, directory)` reads a library, writes it back, diffs the result with the
  original (`diff_umi`), and writes each archetype read and reads it back to diff it with
  itself (`diff_archetypes`). Every difference must appear in a loss of the matching report,
  by subject and location; every loss must match a difference or a value with no counterpart.
- `audit_archetypes(items, directory)` does the archetype half for archetypes or reductions
  (SC-004).

A difference is *explained* by a loss when the loss names the same subject (or the whole
library) and its location is the difference's location, a parent of it, or a reference field
through which the difference was reached (`Difference.via`). A rename (`names.collision`) also
explains a difference whose values are the name before and after, or a name read back from the
renamed component (`"<name> occupancy"`). A numeric difference within
`rel_tol` (SC-003's 0.01 %) is numerical noise, not a loss.

Each function returns the problems found, as readable lines; an empty list passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from archetypal.umi import dialects, read_umi, to_umi
from archetypal.umi.diff import Difference, diff_archetypes, diff_umi
from archetypal.umi.report import LossKind, Note
from archetypal.umi.write import _core_perimeter  # pyright: ignore[reportPrivateUsage]  # the layout write uses

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from epinterface.sbem.archetype import Archetype

    from archetypal.umi.report import Loss
    from archetypal.umi.write import ArchetypeLike

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "umi"
SAMPLES = ("BostonTemplateLibrary_2.json", "BostonTemplateLibrary_nodup.json", "umi_samples_BostonTemplateLibrary.json")
"""The three real libraries of the UMI test set (research R18)."""
EDGE_READABLE = (
    "archsim_dialect.json",
    "duplicate_names.json",
    "misaligned_parts.json",
    "no_templates.json",
    "shared_zone.json",
    "unused_components.json",
)
"""The hand-made edge cases that read without error (the others are refused by design)."""
TEST_SET: tuple[Path, ...] = (
    *(FIXTURES / name for name in SAMPLES),
    *(FIXTURES / "edge" / name for name in EDGE_READABLE),
)
"""Every library of the UMI test set that reads, in a stable order."""

REL_TOL = 1e-4
"""SC-003's tolerance: numeric differences within it are not losses."""

# Losses of a value that has no counterpart on the other side, so no difference can show them.
_NO_COUNTERPART_KINDS = frozenset({LossKind.UNUSED, LossKind.SHARE_DROPPED, LossKind.SKIPPED_TEMPLATE})


def _within(location: str, parent: str, separator: str) -> bool:
    """Whether `location` is `parent` or below it."""
    return location == parent or location.startswith((parent + separator, parent + "["))


def _same_subject(entry: Loss | Note, difference: Difference) -> bool:
    return entry.subject in {"", difference.subject}


def _at(entry: Loss | Note, difference: Difference) -> bool:
    if not _same_subject(entry, difference):
        return False
    separator = "/" if entry.location.startswith("/") else "."
    return any(_within(place, entry.location, separator) for place in (difference.location, *difference.via))


def _explains_unset(note: Note, difference: Difference) -> bool:
    """A value SBEM leaves unset (`None`) that writing fills is an assumption, not a loss.

    A note listing field names (`Findings.unset`) covers those fields only.
    """
    if difference.original is not None or not _at(note, difference):
        return False
    if isinstance(note.value, list) and difference.location != note.location:
        rest = difference.location[len(note.location) + 1 :]
        return any(rest == key or rest.startswith((key + ".", key + "[")) for key in map(str, note.value))
    return True


def _explains_rename(loss: Loss, difference: Difference) -> bool:
    """A renamed component, or a name read back from it (`"<name> occupancy"`)."""
    if not isinstance(loss.value, str):
        return False
    original, result = difference.original, difference.result
    return (
        isinstance(original, str)
        and isinstance(result, str)
        and original.startswith(loss.value)
        and result == f"{loss.replacement}{original[len(loss.value) :]}"
    )


def explains(entry: Loss | Note, difference: Difference) -> bool:
    """Whether a loss, or a note for a value the source did not set, accounts for a difference."""
    if isinstance(entry, Note):
        return _explains_unset(entry, difference)
    if _at(entry, difference):
        return True
    if entry.kind is LossKind.COPIED and difference.original is None:
        # A single group is written as both zones: the zone it was copied to reads back as a group.
        return _same_subject(entry, difference) and difference.location == str(entry.replacement).lower()
    return entry.kind is LossKind.RENAMED and _explains_rename(entry, difference)


def _matches(loss: Loss, difference: Difference) -> bool:
    """Whether a difference shows a loss: `explains`, or the loss is below the difference."""
    if explains(loss, difference):
        return True
    if not _same_subject(loss, difference):
        return False
    separator = "/" if loss.location.startswith("/") else "."
    return _within(loss.location, difference.location, separator)


def _prefixes(location: str) -> list[str]:
    """`location` and every location it is below (`_within`), for both separators."""
    found = [location]
    for index, character in enumerate(location):
        if index and character in "./[":
            found.append(location[:index])
    return found


def _by_location(losses: Iterable[Loss]) -> dict[str, set[str]]:
    """Each loss location → the subjects of the losses there."""
    located: dict[str, set[str]] = {}
    for loss in losses:
        located.setdefault(loss.location, set()).add(loss.subject)
    return located


def _located_at(located: Mapping[str, set[str]], difference: Difference) -> bool:
    """Whether a loss is at or above the difference (`_at`), found by location."""
    for place in (difference.location, *difference.via):
        for prefix in _prefixes(place):
            subjects = located.get(prefix)
            if subjects and ("" in subjects or difference.subject in subjects):
                return True
    return False


@dataclass
class Audit:
    """What one audit found."""

    problems: list[str] = field(default_factory=list[str])
    differences: int = 0
    losses: int = 0
    libraries: list[Path] = field(default_factory=list[Path])
    """The libraries the audit wrote, for `--write-libraries` (`save_library`)."""

    def unexplained(self, differences: Iterable[Difference], losses: Sequence[Loss | Note], what: str) -> None:
        located = _by_location(entry for entry in losses if not isinstance(entry, Note))
        for difference in differences:
            self.differences += 1
            if _located_at(located, difference):  # the common case, without scanning every loss
                continue
            if not any(explains(loss, difference) for loss in losses):
                self.problems.append(
                    f"{what}: unreported difference at {difference.location} (subject {difference.subject!r}, "
                    f"{difference.relevance.value}): {difference.original!r} -> {difference.result!r}"
                )

    def unmatched(
        self, losses: Iterable[Loss], differences: Sequence[Difference], what: str, no_counterpart: set[str]
    ) -> None:
        prefixes: dict[str, set[str]] = {}
        for difference in differences:
            places = prefixes.setdefault(difference.subject, set())
            for place in (difference.location, *difference.via):
                places.update(_prefixes(place))
        for loss in losses:
            self.losses += 1
            if loss.kind in _NO_COUNTERPART_KINDS or loss.upstream is not None or loss.location in no_counterpart:
                continue
            if loss.rule.startswith("layout.") or loss.rule == "names.collision":
                continue
            if loss.location in prefixes.get(loss.subject, set()):
                continue  # a difference at or below the loss
            if not any(_matches(loss, difference) for difference in differences):
                self.problems.append(
                    f"{what}: loss at {loss.location} (subject {loss.subject!r}, rule {loss.rule}) "
                    "matches no difference"
                )


def audit_library(path: Path, directory: Path) -> Audit:
    """Audit one UMI library (SC-006): read, write back, diff both ways."""
    audit = Audit()
    imported = read_umi(path)
    if not imported.archetypes:
        return audit
    exported = to_umi(imported.archetypes)
    written = directory / f"{path.stem}.round-trip.json"
    written.write_text(exported.text, encoding="utf-8")
    audit.libraries.append(written)
    losses = [*imported.report.losses, *exported.report.losses, *exported.report.notes]

    library_diff = diff_umi(path, written, rel_tol=REL_TOL)
    beyond = library_diff.beyond()
    audit.unexplained(beyond, losses, path.name)
    archsim = {pointer for pointer, _ in dialects.load(path).lost}
    umi_losses = [loss for loss in imported.report.losses if loss.location.startswith("/")]
    audit.unmatched(umi_losses, beyond, path.name, archsim)

    back = read_umi(written)
    for original, again in zip(imported.archetypes, back.archetypes, strict=True):
        archetype_diff = diff_archetypes(original, again, rel_tol=REL_TOL).beyond()
        audit.unexplained(
            archetype_diff, [*exported.report.losses, *exported.report.notes], f"{path.name} ({original.Name})"
        )
    return audit


def audit_archetypes(items: Sequence[ArchetypeLike], directory: Path, name: str = "archetypes") -> Audit:
    """Audit archetypes or reductions (SC-004): write, read back, diff with the core/perimeter archetype."""
    audit = Audit()
    exported = to_umi(items)
    written = directory / f"{name}.json"
    written.write_text(exported.text, encoding="utf-8")
    audit.libraries.append(written)
    back = read_umi(written)
    losses = [*exported.report.losses, *exported.report.notes]
    for item, again in zip(items, back.archetypes, strict=True):
        original: Archetype = _core_perimeter(item).archetype
        archetype_diff = diff_archetypes(original, again, rel_tol=REL_TOL).beyond()
        audit.unexplained(archetype_diff, losses, f"{name} ({original.Name})")
        sbem_losses = [loss for loss in exported.report.losses if loss.subject == original.Name]
        audit.unmatched(sbem_losses, archetype_diff, f"{name} ({original.Name})", set())
    return audit
