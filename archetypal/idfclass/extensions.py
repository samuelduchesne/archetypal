"""Eppy extensions module."""

import copy

from eppy.bunch_subclass import BadEPFieldError
from eppy.EPlusInterfaceFunctions.eplusdata import Eplusdata, Idd, removecomment
from geomeppy.patches import EpBunch

from archetypal.utils import extend_class, log


@extend_class(EpBunch)
def __eq__(self, other):
    """Test the equality of two EpBunch objects using all attribute values."""
    if not isinstance(other, EpBunch):
        return False
    return all(str(a).upper() == str(b).upper() for a, b in zip(self.obj, other.obj))


@extend_class(EpBunch)
def nameexists(self):
    """Return True if EpBunch Name already exists in idf.idfobjects[KEY]."""
    existing_objs = self.theidf.idfobjects[self.key.upper()]
    try:
        return self.Name.upper() in [obj.Name.upper() for obj in existing_objs]
    except BadEPFieldError:
        return False


@extend_class(EpBunch)
def get_default(self, name):
    """Return the default value of a field"""
    if "default" in self.getfieldidd(name).keys():
        _type = _parse_idd_type(self, name)
        default_ = next(iter(self.getfieldidd_item(name, "default")), None)
        return _type(default_)
    else:
        return ""


@extend_class(Eplusdata)
def makedict(self, dictfile, fnamefobject):
    """stuff file data into the blank dictionary."""
    # fname = './exapmlefiles/5ZoneDD.idf'
    # fname = './1ZoneUncontrolled.idf'
    if isinstance(dictfile, Idd):
        localidd = copy.deepcopy(dictfile)
        dt, dtls = localidd.dt, localidd.dtls
    else:
        dt, dtls = self.initdict(dictfile)
    fnamefobject.seek(0)  # make sure to read from the beginning
    astr = fnamefobject.read()
    try:
        astr = astr.decode("ISO-8859-2")
    except AttributeError:
        pass
    nocom = removecomment(astr, "!")
    idfst = nocom
    # alist = string.split(idfst, ';')
    alist = idfst.split(";")
    lss = []
    for element in alist:
        # lst = string.split(element, ',')
        lst = element.split(",")
        lss.append(lst)

    for i in range(0, len(lss)):
        for j in range(0, len(lss[i])):
            lss[i][j] = lss[i][j].strip()

    for element in lss:
        node = element[0].upper()
        if node in dt:
            # stuff data in this key
            dt[node.upper()].append(element)
        else:
            # scream
            if node == "":
                continue
            log("this node -%s-is not present in base dictionary" % node)

    self.dt, self.dtls = dt, dtls
    return dt, dtls


def _parse_idd_type(epbunch, name):
    """Parse the fieldvalue type into a python type.

    Possible types are:
        - integer -> int
        - real -> float
        - alpha -> str          (arbitrary string),
        - choice -> str         (alpha with specific list of choices, see \key)
        - object-list -> str    (link to a list of objects defined elsewhere, see \object-list and \reference)
        - external-list -> str  (uses a special list from an external source, see \external-list)
        - node -> str           (name used in connecting HVAC components)
    """
    _type = next(iter(epbunch.getfieldidd_item(name, "type")), "").lower()
    if _type == "real":
        return float
    elif _type == "alpha":
        return str
    elif _type == "integer":
        return int
    else:
        return str


# relationship between epbunch output frequency and db.
bunch2db = {
    "Detailed": ["HVAC System Timestep", "Zone Timestep"],
    "Timestep": ["HVAC System Timestep", "Zone Timestep"],
    "Hourly": "Hourly",
    "Daily": "Daily",
    "Monthly": "Monthly",
    "RunPeriod": "Run Period",
    "Environment": "Run Period",
    "Annual": "Annual",
}
