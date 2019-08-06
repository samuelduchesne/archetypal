################################################################################
# Module: core.py
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import logging as lg

import numpy as np
import pandas as pd

from archetypal import log
from archetypal import weighted_mean, top


def nominal_nat_ventilation(df):
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_natvent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_natvent


def nominal_mech_ventilation(df):
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_vent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: ~e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_vent


def nominal_infiltration(df):
    """Nominal Infiltration

    Args:
        df:

    Returns:
        df

    References:
        * `Nominal Infiltration Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalinfiltration-table>`_

    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneInfiltration Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])

    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )
    tbpiv.replace({"N/A": np.nan}, inplace=True)
    return (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name"])
        .agg(lambda x: pd.to_numeric(x, errors="ignore").sum())
    )


def nominal_ventilation(df):
    """Nominal Ventilation

    Args:
        df:

    Returns:
        df

    References:
        * `Nominal Ventilation Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalventilation-table>`_

    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneVentilation Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])
    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )

    tbpiv = tbpiv.replace({"N/A": np.nan}).apply(
        lambda x: pd.to_numeric(x, errors="ignore")
    )
    tbpiv = (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name", "Fan Type {Exhaust;Intake;Natural}"])
        .apply(nominal_ventilation_aggregation)
    )
    return tbpiv
    # .reset_index().groupby(['Archetype', 'Zone Name']).agg(
    # lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_ventilation_aggregation(x):
    """Aggregates the ventilations whithin a single zone_loads name (implies
    that
    .groupby(['Archetype', 'Zone Name']) is
    performed before calling this function).

    Args:
        x:

    Returns:
        A DataFrame with at least one entry per ('Archetype', 'Zone Name'),
        aggregated accordingly.
    """
    how_dict = {
        "Name": top(x["Name"], x, "Zone Floor Area {m2}"),
        "Schedule Name": top(x["Schedule Name"], x, "Zone Floor Area {m2}"),
        "Zone Floor Area {m2}": top(
            x["Zone Floor Area {m2}"], x, "Zone Floor Area {m2}"
        ),
        "# Zone Occupants": top(x["# Zone Occupants"], x, "Zone Floor Area {m2}"),
        "Design Volume Flow Rate {m3/s}": weighted_mean(
            x["Design Volume Flow Rate {m3/s}"], x, "Zone Floor Area {m2}"
        ),
        "Volume Flow Rate/Floor Area {m3/s/m2}": weighted_mean(
            x["Volume Flow Rate/Floor Area {m3/s/m2}"], x, "Zone Floor Area {m2}"
        ),
        "Volume Flow Rate/person Area {m3/s/person}": weighted_mean(
            x["Volume Flow Rate/person Area {m3/s/person}"], x, "Zone Floor Area {m2}"
        ),
        "ACH - Air Changes per Hour": weighted_mean(
            x["ACH - Air Changes per Hour"], x, "Zone Floor Area {m2}"
        ),
        "Fan Pressure Rise {Pa}": weighted_mean(
            x["Fan Pressure Rise {Pa}"], x, "Zone Floor Area {m2}"
        ),
        "Fan Efficiency {}": weighted_mean(
            x["Fan Efficiency {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation A - Constant Term Coefficient {}": top(
            x["Equation A - Constant Term Coefficient {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation B - Temperature Term Coefficient {1/C}": top(
            x["Equation B - Temperature Term Coefficient {1/C}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Equation C - Velocity Term Coefficient {s/m}": top(
            x["Equation C - Velocity Term Coefficient {s/m}"], x, "Zone Floor Area {m2}"
        ),
        "Equation D - Velocity Squared Term Coefficient {s2/m2}": top(
            x["Equation D - Velocity Squared Term Coefficient {s2/m2}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Minimum Indoor Temperature{C}/Schedule": top(
            x["Minimum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Indoor Temperature{C}/Schedule": top(
            x["Maximum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Delta Temperature{C}/Schedule": top(
            x["Delta Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Minimum Outdoor Temperature{C}/Schedule": top(
            x["Minimum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Outdoor Temperature{C}/Schedule": top(
            x["Maximum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum WindSpeed{m/s}": top(
            x["Maximum WindSpeed{m/s}"], x, "Zone Floor Area {m2}"
        ),
    }
    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        print("{}".format(e))
    else:
        return df


def get_from_tabulardata(results):
    """Returns a DataFrame from the 'TabularDataWithStrings' table. A
    multiindex is returned with names ['Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    tab_data_wstring = pd.concat(
        [value["TabularDataWithStrings"] for value in results.values()],
        keys=results.keys(),
        names=["Archetype"],
    )
    tab_data_wstring.index.names = ["Archetype", "Index"]  #
    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring


def get_from_reportdata(results):
    """Returns a DataFrame from the 'ReportData' table. A multiindex is
    returned with names ['Archetype', 'Index']

    Args:
        results:

    Returns:

    """
    report_data = pd.concat(
        [value["ReportData"] for value in results.values()],
        keys=results.keys(),
        names=["Archetype"],
    )
    report_data["ReportDataDictionaryIndex"] = pd.to_numeric(
        report_data["ReportDataDictionaryIndex"]
    )

    report_data_dict = pd.concat(
        [value["ReportDataDictionary"] for value in results.values()],
        keys=results.keys(),
        names=["Archetype"],
    )

    return report_data.reset_index().join(
        report_data_dict, on=["Archetype", "ReportDataDictionaryIndex"]
    )
