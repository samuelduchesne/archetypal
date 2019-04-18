from archetypal import settings


class UmiBase(object):
    def __init__(self, Name='unnamed', Comment='', DataSource='',
                 Archetype=None, **kwargs):
        self.Comment = Comment
        self.DataSource = DataSource
        self.Name = Name
        self.Archetype = Archetype

    @property
    def id(self):
        return id(self)


class MaterialsGas(UmiBase):
    """
    $id, Comment, Cost, DataSource, EmbodiedCarbon, EmbodiedCarbonStdDev,
    EmbodiedEnergy, EmbodiedEnergyStdDev, GasType, Life, Name,
    SubstitutionRatePattern, SubstitutionTimestep, TransportCarbon,
    TransportDistance, TransportEnergy, Type
    """

    def __init__(self, *args,
                 Cost=0,
                 EmbodiedCarbon=0,
                 EmbodiedCarbonStdDev=0,
                 EmbodiedEnergy=0,
                 EmbodiedEnergyStdDev=0,
                 Gas_Type=None,
                 Life=1,
                 SubstitutionRatePattern=[],
                 SubstitutionTimestep=0,
                 TransportCarbon=0,
                 TransportDistance=0,
                 TransportEnergy=0,
                 Type='Gas',
                 **kwargs):
        super(MaterialsGas, self).__init__(*args,
                                           **kwargs)

        self.cols_ = settings.common_umi_objects['GasMaterials']
        self.Cost = Cost
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedCarbonStdDev = EmbodiedCarbonStdDev
        self.EmbodiedEnergy = EmbodiedEnergy
        self.EmbodiedEnergyStdDev = EmbodiedEnergyStdDev
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy
        self.Life = Life
        self.Type = Type
        self.GasType = self._gas_type(Gas_Type)
        self.DataSource = self.Archetype  # Use the Archetype Name as a
        # DataSource

        # TODO: What does Life mean? Always 1 in Boston UmiTemplate

    @staticmethod
    def _gas_type(Gas_Type):
        """Return the UMI gas type number

        Args:
            self (pandas.DataFrame):name

        Returns:
            int: UMI gas type number. The return number is specific to the
            umi api.

        """
        if 'air' in Gas_Type.lower():
            return 0
        elif 'argon' in Gas_Type.lower():
            return 1
        elif 'krypton' in Gas_Type.lower():
            return 2
        elif 'xenon' in Gas_Type.lower():
            return 3
        elif 'sf6' in Gas_Type.lower():
            return 4
