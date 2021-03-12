import functools
import time

import numpy as np
import pandas as pd

from archetypal.utils import log


class TabularData(pd.DataFrame):
    """This class serves as a subclass of a pandas DataFrame allowing to add
    additional functionnality
    """

    ARCHETYPE = "Archetype"
    TABULARDATAINDEX = "TabularDataIndex"
    VALUE = "Value"
    REPORTNAME = "ReportName"
    REPORTFORSTRING = "ReportForString"
    TABLENAME = "TableName"
    ROWNAME = "RowName"
    COLUMNNAME = "ColumnName"
    UNITS = "Units"

    @classmethod
    def from_sql(cls, sql_dict):
        """Returns a DataFrame from the 'TabularDataWithStrings' table

        Args:
            sql_dict:
        """

        tab_data_wstring = sql_dict["TabularDataWithStrings"]
        tab_data_wstring.index.names = ["Index"]

        # strip whitespaces
        tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
        tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()

        return cls(tab_data_wstring)

    @property
    def _constructor(self):
        return TabularData

    @property
    def df(self):
        """Returns the DataFrame of the ReportData"""
        return pd.DataFrame(self)

    def filter_tabular_data(
        self,
        archetype=None,
        tabulardataindex=None,
        value=None,
        reportname=None,
        reportforstring=None,
        tablename=None,
        rowname=None,
        columnname=None,
        units=None,
        inplace=False,
    ):
        """filter RaportData using specific keywords. Each keywords can be a
        tuple of strings (str1, str2, str3) which will return the logical_or on
        the specific column.

        Args:
            archetype (str or tuple):
            tabulardataindex:
            value (str or tuple):
            reportname:
            reportforstring:
            tablename:
            rowname:
            columnname:
            units (str or tuple):
            inplace (str or tuple):

        Returns:
            pandas.DataFrame
        """
        start_time = time.time()
        c_n = []

        if archetype:
            c_1 = (
                conjunction(
                    *[self[self.ARCHETYPE] == archetype for archetype in archetype],
                    logical=np.logical_or
                )
                if isinstance(archetype, tuple)
                else self[self.ARCHETYPE] == archetype
            )
            c_n.append(c_1)
        if tabulardataindex:
            c_2 = (
                conjunction(
                    *[
                        self[self.TABULARDATAINDEX] == tabulardataindex
                        for tabulardataindex in tabulardataindex
                    ],
                    logical=np.logical_or
                )
                if isinstance(tabulardataindex, tuple)
                else self[self.TABULARDATAINDEX] == tabulardataindex
            )
            c_n.append(c_2)
        if value:
            c_3 = (
                conjunction(
                    *[self[self.VALUE] == value for value in value],
                    logical=np.logical_or
                )
                if isinstance(value, tuple)
                else self[self.VALUE] == value
            )
            c_n.append(c_3)
        if reportname:
            c_4 = (
                conjunction(
                    *[self[self.REPORTNAME] == reportname for reportname in reportname],
                    logical=np.logical_or
                )
                if isinstance(reportname, tuple)
                else self[self.REPORTNAME] == reportname
            )
            c_n.append(c_4)
        if value:
            c_5 = (
                conjunction(
                    *[self[self.VALUE] == value for value in value],
                    logical=np.logical_or
                )
                if isinstance(value, tuple)
                else self[self.VALUE] == value
            )
            c_n.append(c_5)
        if reportforstring:
            c_6 = (
                conjunction(
                    *[
                        self[self.REPORTFORSTRING] == reportforstring
                        for reportforstring in reportforstring
                    ],
                    logical=np.logical_or
                )
                if isinstance(reportforstring, tuple)
                else self[self.REPORTFORSTRING] == reportforstring
            )
            c_n.append(c_6)
        if tablename:
            c_7 = (
                conjunction(
                    *[self[self.TABLENAME] == tablename for tablename in tablename],
                    logical=np.logical_or
                )
                if isinstance(tablename, tuple)
                else self[self.TABLENAME] == tablename
            )
            c_n.append(c_7)
        if rowname:
            c_8 = (
                conjunction(
                    *[self[self.ROWNAME] == rowname for rowname in rowname],
                    logical=np.logical_or
                )
                if isinstance(rowname, tuple)
                else self[self.ROWNAME] == rowname
            )
            c_n.append(c_8)
        if columnname:
            c_9 = (
                conjunction(
                    *[self[self.COLUMNNAME] == columnname for columnname in columnname],
                    logical=np.logical_or
                )
                if isinstance(columnname, tuple)
                else self[self.COLUMNNAME] == columnname
            )
            c_n.append(c_9)
        if units:
            c_14 = (
                conjunction(
                    *[self[self.UNITS] == units for units in units],
                    logical=np.logical_or
                )
                if isinstance(units, tuple)
                else self[self.UNITS] == units
            )
            c_n.append(c_14)

        filtered_df = self.loc[conjunction(*c_n, logical=np.logical_and)]
        log("filtered TabularData in {:,.2f} seconds".format(time.time() - start_time))
        if inplace:
            return filtered_df._update_inplace(filtered_df)
        else:
            return filtered_df._constructor(filtered_df).__finalize__(self)


def conjunction(*conditions, logical=np.logical_and):
    """Applies a logical function on n conditons

    Args:
        *conditions:
        logical:
    """
    return functools.reduce(logical, conditions)


def or_conjunction(*conditions):
    """
    Args:
        *conditions:
    """
    return functools.reduce(np.logical_or, conditions)
