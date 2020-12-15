"""eppy extensions."""
from opyplus.epm.record import Record

# Expose objls like Epbunch.objls
Record.objls = property(lambda self: list(self))
