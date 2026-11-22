"""Layouts and the options of a reduction (spec 002, data-model.md: Layout and ReductionOptions).

A layout decides how conditioned zones are grouped. Each layout keeps some of the two
distinctions reduction knows, a zone's space use and its exposure (core or perimeter), and
its group key is the tuple of the distinctions it keeps:

| Layout | Group key |
|---|---|
| `SPACE_USE_EXPOSURE` (default) | `(space_use, exposure)` |
| `SPACE_USE` | `(space_use,)` |
| `CORE_PERIMETER` | `(exposure,)` |
| `SINGLE_ZONE` | `()` |

Layouts form a partial order by coarseness: a layout is finer than or equal to another when
it keeps every distinction the other keeps. `SPACE_USE` and `CORE_PERIMETER` are not
comparable. `merge` refuses only a target strictly finer than the source
(`Layout.is_strictly_finer`), because the report keeps its ledgers at the finest key.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping  # noqa: TC003 - pydantic resolves annotations at run time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10 has no StrEnum

    class StrEnum(str, Enum):
        """A `str` enum whose `str()` is its value, as Python 3.11's `enum.StrEnum`."""

        def __str__(self) -> str:
            """Return the member's value."""
            return str(self.value)


__all__ = ["Distinction", "Exposure", "GroupKey", "Layout", "ReductionOptions"]

Exposure = Literal["perimeter", "core"]
"""A conditioned zone's exposure (research R7)."""

Distinction = Literal["space_use", "exposure"]
"""A distinction between zones that a layout keeps or loses, in group-key order."""

GroupKey = tuple[str, ...]
"""A group key: the values of the distinctions a layout keeps, in `Distinction` order."""

_ORDER: tuple[Distinction, ...] = ("space_use", "exposure")


class Layout(StrEnum):
    """How conditioned zones are grouped into SBEM zone groups.

    Attributes:
        SPACE_USE_EXPOSURE: One group per space use and exposure (the default, the finest).
        SPACE_USE: One group per space use.
        CORE_PERIMETER: One group per exposure.
        SINGLE_ZONE: One group for the whole building (the coarsest).
    """

    SPACE_USE_EXPOSURE = "space_use_exposure"
    SPACE_USE = "space_use"
    CORE_PERIMETER = "core_perimeter"
    SINGLE_ZONE = "single_zone"

    @property
    def distinctions(self) -> tuple[Distinction, ...]:
        """The distinctions this layout keeps, in group-key order."""
        return _DISTINCTIONS[self]

    def group_key(self, space_use: str, exposure: Exposure) -> GroupKey:
        """Return the group key of a zone with this space use and exposure.

        Args:
            space_use: The zone's space use.
            exposure: The zone's exposure.

        Returns:
            The values of the distinctions this layout keeps, in `Distinction` order.
        """
        values: dict[Distinction, str] = {"space_use": space_use, "exposure": exposure}
        return tuple(values[d] for d in self.distinctions)

    def regroup(self, finest_key: GroupKey) -> GroupKey:
        """Return this layout's key for a key of the finest layout, `SPACE_USE_EXPOSURE`.

        `merge` uses it to regroup the report's pre-threshold ledgers.

        Args:
            finest_key: A `(space_use, exposure)` key.

        Returns:
            The same key as `group_key` gives for that zone.

        Raises:
            ValueError: If `finest_key` does not have two items.
        """
        if len(finest_key) != len(_ORDER):
            msg = f"{finest_key!r}: a finest group key has {len(_ORDER)} items (space use, exposure)"
            raise ValueError(msg)
        values = dict(zip(_ORDER, finest_key, strict=False))
        return tuple(values[d] for d in self.distinctions)

    def is_finer_or_equal(self, other: Layout) -> bool:
        """Whether this layout keeps every distinction `other` keeps (`self` ≤ `other`).

        Args:
            other: The layout to compare with.

        Returns:
            `True` when this layout is finer than or equal to `other`.
        """
        return set(other.distinctions) <= set(self.distinctions)

    def is_strictly_finer(self, other: Layout) -> bool:
        """Whether this layout is strictly finer than `other` (`self` < `other`).

        Called as `Layout.is_strictly_finer(a, b)`. `merge` refuses a target layout that is
        strictly finer than the source's.

        Args:
            other: The layout to compare with.

        Returns:
            `True` when this layout keeps every distinction `other` keeps, and more.
        """
        return set(other.distinctions) < set(self.distinctions)

    def is_comparable(self, other: Layout) -> bool:
        """Whether the two layouts are ordered by coarseness, one way or the other.

        Args:
            other: The layout to compare with.

        Returns:
            `False` only for `SPACE_USE` against `CORE_PERIMETER`.
        """
        return self.is_finer_or_equal(other) or other.is_finer_or_equal(self)

    def lost_from(self, source: Layout) -> tuple[Distinction, ...]:
        """The distinctions `source` keeps that this layout loses, in group-key order.

        Args:
            source: The layout regrouped into this one.

        Returns:
            The lost distinctions, as the report's `merged_distinctions[].lost` lists them.
        """
        return tuple(d for d in source.distinctions if d not in self.distinctions)


_DISTINCTIONS: dict[Layout, tuple[Distinction, ...]] = {
    Layout.SPACE_USE_EXPOSURE: ("space_use", "exposure"),
    Layout.SPACE_USE: ("space_use",),
    Layout.CORE_PERIMETER: ("exposure",),
    Layout.SINGLE_ZONE: (),
}


class ReductionOptions(BaseModel):
    """The options of a reduction. Frozen: derive variants with `model_copy(update=...)`.

    Attributes:
        layout: How conditioned zones are grouped.
        small_group_threshold: A share of conditioned floor area in [0, 1). A group smaller
            than this share is merged into its most similar eligible group.
        space_use_mapping: Zone name to space use, overriding the space use reduction
            infers (research R4). `None` infers every space use.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    layout: Layout = Layout.SPACE_USE_EXPOSURE
    small_group_threshold: float = Field(
        default=0.05,
        ge=0.0,
        lt=1.0,
        description="a share of conditioned floor area in [0, 1)",
    )
    space_use_mapping: Mapping[str, str] | None = None
