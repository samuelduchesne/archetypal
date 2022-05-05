"""Eppy extensions module."""

import copy

from eppy.bunch_subclass import BadEPFieldError
from eppy.EPlusInterfaceFunctions.eplusdata import Eplusdata, Idd, removecomment
from eppy.idf_msequence import Idf_MSequence
from geomeppy.patches import EpBunch

from archetypal.utils import extend_class, log


@extend_class(EpBunch)
def __eq__(self: EpBunch, other):
    """Test the equality of two EpBunch objects using all attribute values."""
    if not isinstance(other, EpBunch):
        return False
    return all(str(a).upper() == str(b).upper() for a, b in zip(self.obj, other.obj))


@extend_class(EpBunch)
def nameexists(self: EpBunch):
    """Return True if EpBunch Name already exists in idf.idfobjects[KEY]."""
    existing_objs = self.theidf.idfobjects[self.key.upper()]
    try:
        return self.Name.upper() in [obj.Name.upper() for obj in existing_objs]
    except BadEPFieldError:
        return False


@extend_class(EpBunch)
def get_default(self: EpBunch, name):
    """Return the default value of a field"""
    if "default" in self.getfieldidd(name).keys():
        _type = _parse_idd_type(self, name)
        default_ = next(iter(self.getfieldidd_item(name, "default")), None)
        return _type(default_)
    else:
        return ""


@extend_class(EpBunch)
def to_dict(self: EpBunch):
    """Get the dict representation of the EpBunch."""
    return {k: v for k, v in zip(self.fieldnames, self.fieldvalues)}


@extend_class(EpBunch)
def __init__(self, obj, objls, objidd, *args, **kwargs):
    """Extension of EpBunch to add daylighting:referencepoints coords."""
    super(EpBunch, self).__init__(obj, objls, objidd, *args, **kwargs)
    if self.key.upper() == "DAYLIGHTING:REFERENCEPOINT":
        func_dict = {
            "coords": get_coords,
        }
        self.__functions.update(func_dict)


def get_coords(obj: EpBunch):
    """Return tuple of X, Y, Z"""
    return [
        (
            obj.XCoordinate_of_Reference_Point,
            obj.YCoordinate_of_Reference_Point,
            obj.ZCoordinate_of_Reference_Point,
        ),
    ]


@extend_class(Idf_MSequence)
def to_dict(self: Idf_MSequence):
    """Get the list of dict representation of the Idf_Msequence."""
    return [obj.to_dict() for obj in self]


@extend_class(Eplusdata)
def makedict(self: Eplusdata, dictfile, fnamefobject):
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


def get_name_attribute(__o: EpBunch):
    try:
        return getattr(__o, "Key_Name")
    except BadEPFieldError:  # Backwards compatibility
        return getattr(__o, "Name")
