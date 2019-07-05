################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
from enum import IntEnum

from archetypal.template import MaterialLayer
from archetypal.template.gas_material import GasMaterial
from archetypal.template.glazing_material import GlazingMaterial
from archetypal.template.umi_base import UmiBase, Unique
from archetypal.idfclass import IDF


class WindowConstruction(UmiBase, metaclass=Unique):
    """
    $id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, Layers, Name, Type
    """

    def __init__(self, AssemblyCarbon=0, AssemblyCost=0,
                 AssemblyEnergy=0, DisassemblyCarbon=0,
                 DisassemblyEnergy=0, **kwargs):
        """Initialize a WindowConstruction.

        Args:
            AssemblyCarbon (float): Assembly Embodied Carbon by m2 of
                construction.
            AssemblyCost (float): Assembly cost by m2 of construction.
            AssemblyEnergy (float): Assembly Embodied Energy by m2; of
                construction.
            DisassemblyCarbon (float): Disassembly embodied carbon by m2 of
                construction.
            DisassemblyEnergy (float): Disassembly embodied energy by m2 of
                construction.
            **kwargs: Other keywords passed to the constructor.
        """
        super(WindowConstruction, self).__init__(**kwargs)
        self.DisassemblyEnergy = DisassemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.AssemblyEnergy = AssemblyEnergy
        self.AssemblyCost = AssemblyCost
        self.AssemblyCarbon = AssemblyCarbon
        self.Layers = None

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        wc = cls(*args, **kwargs)
        layers = kwargs.get('Layers', None)

        # resolve Material objects from ref
        wc.Layers = [MaterialLayer(wc.get_ref(layer['Material']),
                                   layer['Thickness'])
                     for layer in layers]
        return wc

    @classmethod
    def from_idf(cls, Name, idf, **kwargs):
        """WindowConstruction from idf Construction Name.

        Example:
            >>> import archetypal as ar
            >>> idf = ar.load_idf("myidf")
            >>> construction_name = "Some construction name"
            >>> ar.WindowConstruction.from_idf(Name=construction_name, idf=idf)

        Args:
            Name (str): The name of the Construction in the IDF file.
            idf (IDF): The idf object.
            **kwargs: Other keywords passed to the constructor.
        """
        wc = cls(Name=Name, idf=idf, **kwargs)
        wc.Layers = wc.layers()

        return wc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [layer.to_dict()
                               for layer in self.Layers]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def layers(self):
        """Retrieve layers for the WindowConstruction"""
        c = self.idf.getobject('CONSTRUCTION', self.Name)
        layers = []
        for field in c.fieldnames:
            # Loop through the layers from the outside layer towards the
            # indoor layers and get the material they are made of.
            material = c.get_referenced_object(field)
            if material:
                # Create the WindowMaterial:Glazing or the WindowMaterial:Gas
                # and append to the list of layers
                material_obj = GlazingMaterial(Name=material.Name,
                                               Conductivity=material.Conductivity,
                                               Optical=material.Optical_Data_Type,
                                               OpticalData=material.Window_Glass_Spectral_Data_Set_Name,
                                               SolarTransmittance=material.Solar_Transmittance_at_Normal_Incidence,
                                               SolarReflectanceFront=material.Front_Side_Solar_Reflectance_at_Normal_Incidence,
                                               SolarReflectanceBack=material.Back_Side_Solar_Reflectance_at_Normal_Incidence,
                                               VisibleTransmittance=material.Visible_Transmittance_at_Normal_Incidence,
                                               VisibleReflectanceFront=material.Front_Side_Visible_Reflectance_at_Normal_Incidence,
                                               VisibleReflectanceBack=material.Back_Side_Visible_Reflectance_at_Normal_Incidence,
                                               IRTransmittance=material.Infrared_Transmittance_at_Normal_Incidence,
                                               IREmissivityFront=material.Front_Side_Infrared_Hemispherical_Emissivity,
                                               IREmissivityBack=material.Back_Side_Infrared_Hemispherical_Emissivity,
                                               DirtFactor=material.Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance,
                                               Type='Uncoated', idf=self.idf) \
                    if \
                    material.obj[
                        0].upper() == 'WindowMaterial:Glazing'.upper() else \
                    GasMaterial(
                        Name=material.Name, idf=self.idf,
                        Gas_Type=material.Gas_Type)
                material_layer = MaterialLayer(material_obj, material.Thickness)
                layers.append(
                    material_layer
                )
        return layers


class WindowType(IntEnum):
    External = 0
    Internal = 1


class WindowSetting(UmiBase, metaclass=Unique):
    """AfnDischargeC, AfnTempSetpoint, AfnWindowAvailability.$ref, Category,
    Comments, OpaqueConstruction.$ref, DataSource, IsShadingSystemOn,
    IsVirtualPartition, IsZoneMixingOn, Name, OperableArea,
    ShadingSystemAvailabilitySchedule.$ref, ShadingSystemSetpoint,
    ShadingSystemTransmittance, ShadingSystemType, Type,
    ZoneMixingAvailabilitySchedule.$ref, ZoneMixingDeltaTemperature,
    ZoneMixingFlowRate
    """

    def __init__(self, Construction=None, OperableArea=0.8,
                 AfnWindowAvailability=None, AfnDischargeC=0.65,
                 AfnTempSetpoint=20, IsVirtualPartition=False,
                 IsShadingSystemOn=False,
                 ShadingSystemAvailabilitySchedule=None,
                 ShadingSystemSetpoint=180, ShadingSystemTransmittance=0.5,
                 ShadingSystemType=0, Type=WindowType.External,
                 IsZoneMixingOn=False, ZoneMixingAvailabilitySchedule=None,
                 ZoneMixingDeltaTemperature=2, ZoneMixingFlowRate=0.001,
                 **kwargs):
        """WindowSetting.

        Args:
            Construction (WindowConstruction): The window construction.
            OperableArea (float): The operable window area as a ratio of total
                window area. eg. 0.8 := 80% of the windows area is operable.
            AfnWindowAvailability:
            AfnDischargeC (float): Airflow Network Discharge Coefficient.
                Default = 0.65.
            AfnTempSetpoint (float): Airflow Network Temperature Setpoint.
                Default = 20 degreeC.
            IsVirtualPartition (bool): Virtual Partition.
            IsShadingSystemOn (bool): Shading is used. Default is False.
            ShadingSystemAvailabilitySchedule (UmiSchedule): Shading system
                availability schedule.
            ShadingSystemSetpoint (float): Shading system setpoint in units of
                W/m2. Default = 180 W/m2.
            ShadingSystemTransmittance (float): Shading system transmittance.
                Default = 0.5.
            ShadingSystemType (int): Shading System Type. 0 = ExteriorShade, 1 =
                InteriorShade.
            Type (int):
            IsZoneMixingOn (bool): Zone mixing.
            ZoneMixingAvailabilitySchedule (UmiSchedule): Zone mixing
                availability schedule.
            ZoneMixingDeltaTemperature (float): Zone mixing delta
            ZoneMixingFlowRate (float): Zone mixing flow rate in units of m3/m2.
                Default = 0.001 m3/m2.
            **kwargs: other keywords passed to the constructor.
        """
        super(WindowSetting, self).__init__(**kwargs)
        self.ZoneMixingAvailabilitySchedule = ZoneMixingAvailabilitySchedule
        self.ShadingSystemAvailabilitySchedule = \
            ShadingSystemAvailabilitySchedule
        self.Construction = Construction
        self.AfnWindowAvailability = AfnWindowAvailability
        self.AfnDischargeC = AfnDischargeC
        self.AfnTempSetpoint = AfnTempSetpoint
        self.IsShadingSystemOn = IsShadingSystemOn
        self.IsVirtualPartition = IsVirtualPartition
        self.IsZoneMixingOn = IsZoneMixingOn
        self.OperableArea = OperableArea
        self.ShadingSystemSetpoint = ShadingSystemSetpoint
        self.ShadingSystemTransmittance = ShadingSystemTransmittance
        self.ShadingSystemType = ShadingSystemType
        self.Type = Type  # Todo: Could be deprecated
        self.ZoneMixingDeltaTemperature = ZoneMixingDeltaTemperature
        self.ZoneMixingFlowRate = ZoneMixingFlowRate

    @classmethod
    def from_idf(cls, Construction, idf, **kwargs):
        """Make a WindowSetting from an idf object. Must provide the
        Construction name.

        Example:
            >>> import archetypal as ar
            >>> # Given an IDF object
            >>> idf = ar.load_idf("idfname")
            >>> ar.WindowSetting.from_idf(Name='test_window', idf=idf,
            >>>                    Construction="AEDG-SmOffice 1A Window Fixed")

        Args:
            Construction (str): The construction name for this window.
            idf (IDF): The idf object.
            **kwargs: Other keywords passed to the constructor.
        """
        w = cls(idf=idf, **kwargs)
        w.Construction = WindowConstruction.from_idf(Name=Construction,
                                                     idf=w.idf)

        return w

    def __add__(self, other):
        if isinstance(other, self.__class__):
            self.AfnDischargeC = max(self.AfnDischargeC, other.AfnDischargeC)
            self.AfnTempSetpoint = max(self.AfnTempSetpoint,
                                       other.AfnTempSetpoint)
            self.IsShadingSystemOn = any([self.IsShadingSystemOn,
                                          other.IsShadingSystemOn])
            self.IsVirtualPartition = any([self.IsVirtualPartition,
                                           other.IsVirtualPartition])
            self.IsZoneMixingOn = any([self.IsZoneMixingOn,
                                       other.IsZoneMixingOn])
            self.OperableArea = max(self.OperableArea,
                                    other.OperableArea)
            self.ShadingSystemSetpoint = max(self.ShadingSystemSetpoint,
                                             other.ShadingSystemSetpoint)
            self.ShadingSystemTransmittance = \
                max(self.ShadingSystemTransmittance,
                    other.ShadingSystemTransmittance)
            self.ShadingSystemType = self.ShadingSystemType
            self.Type = self.Type
            self.ZoneMixingDeltaTemperature = \
                max(self.ZoneMixingDeltaTemperature,
                    other.ZoneMixingDeltaTemperature)
            self.ZoneMixingFlowRate = max(self.ZoneMixingFlowRate,
                                          other.ZoneMixingFlowRate)
            return self
        else:
            raise NotImplementedError

    def __iadd__(self, other):
        if isinstance(other, None):
            return self
        else:
            return self + other

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["AfnDischargeC"] = self.AfnDischargeC
        data_dict["AfnTempSetpoint"] = self.AfnTempSetpoint
        data_dict["AfnWindowAvailability"] = \
            self.AfnWindowAvailability.to_dict()
        data_dict["Construction"] = {
            "$ref": str(self.Construction.id)
        }
        data_dict["IsShadingSystemOn"] = self.IsShadingSystemOn
        data_dict["IsVirtualPartition"] = self.IsVirtualPartition
        data_dict["IsZoneMixingOn"] = self.IsZoneMixingOn
        data_dict["OperableArea"] = self.OperableArea
        data_dict["ShadingSystemAvailabilitySchedule"] = \
            self.ShadingSystemAvailabilitySchedule.to_dict()
        data_dict["ShadingSystemSetpoint"] = self.ShadingSystemSetpoint
        data_dict[
            "ShadingSystemTransmittance"] = self.ShadingSystemTransmittance
        data_dict["ShadingSystemType"] = self.ShadingSystemType
        data_dict["Type"] = self.Type
        data_dict["ZoneMixingAvailabilitySchedule"] = \
            self.ZoneMixingAvailabilitySchedule.to_dict()
        data_dict[
            "ZoneMixingDeltaTemperature"] = self.ZoneMixingDeltaTemperature
        data_dict["ZoneMixingFlowRate"] = self.ZoneMixingFlowRate
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        w = cls(*args, **kwargs)

        ref = kwargs.get('AfnWindowAvailability', None)
        w.AfnWindowAvailability = w.get_ref(ref)
        ref = kwargs.get('Construction', None)
        w.Construction = w.get_ref(ref)
        ref = kwargs.get('ShadingSystemAvailabilitySchedule', None)
        w.ShadingSystemAvailabilitySchedule = w.get_ref(ref)
        ref = kwargs.get('ZoneMixingAvailabilitySchedule', None)
        w.ZoneMixingAvailabilitySchedule = w.get_ref(ref)
        return w

    def __radd__(self, other):
        """
        Args:
            other:
        """
        return self + other
