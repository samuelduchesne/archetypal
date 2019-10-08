import os

import pytest
from archetypal import Schedule, load_idf, copy_file, run_eplus, UmiSchedule, config


def test_schedules_in_necb_specific(config):
    files = [
        "tests/input_data/regular/NECB 2011-MediumOffice-NECB HDD "
        "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
    ]
    idfs = {os.path.basename(file): load_idf(file) for file in files}
    import matplotlib.pyplot as plt

    for key in idfs:
        idf = idfs[key]
        s = Schedule(
            Name="NECB-A-Thermostat Setpoint-Heating", idf=idf, start_day_of_the_week=0
        )
        s.plot(slice=("2018/01/02", "2018/01/03"), drawstyle="steps-post")
        plt.show()


def test_make_umi_schedule(config):
    """Tests only a single schedule name"""
    import matplotlib.pyplot as plt

    idf_file = "tests/input_data/schedules/schedules.idf"
    idf_file = copy_file(idf_file)
    idf = load_idf(idf_file)

    s = UmiSchedule(Name="POFF", idf=idf, start_day_of_the_week=0)
    ep_year, ep_weeks, ep_days = s.to_year_week_day()

    new = UmiSchedule(
        Name=ep_year.Name, idf=idf, start_day_of_the_week=s.startDayOfTheWeek
    )

    print(len(s.all_values))
    print(len(new.all_values))
    ax = s.plot(slice=("2018/01/01 00:00", "2018/01/07"), legend=True)
    new.plot(slice=("2018/01/01 00:00", "2018/01/07"), ax=ax, legend=True)
    plt.show()
    assert s.__class__.__name__ == "UmiSchedule"
    assert len(s.all_values) == len(new.all_values)
    assert (new.all_values == s.all_values).all()


def test_constant_schedule():
    const = Schedule.constant_schedule()
    assert const.__class__.__name__ == "Schedule"


idf_file = "tests/input_data/schedules/test_multizone_EP.idf"


def schedules_idf():
    config(cache_folder="tests/.temp/cache")
    idf = load_idf(
        idf_file, include=["tests/input_data/schedules/TDV_2008_kBtu_CTZ06.csv"]
    )
    return idf


idf = schedules_idf()
schedules = list(idf.get_all_schedules(yearly_only=True).keys())
ids = [i.replace(" ", "_") for i in schedules]
schedules = [
    pytest.param(
        schedule,
        marks=pytest.mark.xfail(
            reason="Can't quite capture all possibilities " "with special days"
        ),
    )
    if schedule == "POFF"
    else pytest.param(schedule, marks=pytest.mark.xfail(raises=NotImplementedError))
    if schedule == "Cooling Setpoint Schedule"
    else schedule
    for schedule in schedules
]


def test_ep_versus_schedule(test_data):
    """Main test. Will run the idf using EnergyPlus, retrieve the csv file,
    create the schedules and compare"""

    orig, new, expected = test_data

    # slice_ = ('2018/01/01 00:00', '2018/01/08 00:00')  # first week
    # slice_ = ('2018/05/20 12:00', '2018/05/22 12:00')
    slice_ = ("2018/04/30 12:00", "2018/05/02 12:00")  # Holiday
    # slice_ = ('2018/01/01 00:00', '2018/12/31 23:00')  # all year
    # slice_ = ('2018/04/30 12:00', '2018/05/01 12:00')  # break

    mask = expected.values != orig.all_values
    diff = mask.sum()

    # # region Plot
    # fig, ax = plt.subplots(1, 1, figsize=(5, 4))
    # orig.plot(slice=slice_, ax=ax, legend=True, drawstyle='steps-post',
    #           linestyle='dashed')
    # new.plot(slice=slice_, ax=ax, legend=True, drawstyle='steps-post',
    #          linestyle='dotted')
    # expected.loc[slice_[0]:slice_[1]].plot(label='E+', legend=True, ax=ax,
    #                                        drawstyle='steps-post',
    #                                        linestyle='dashdot')
    # ax.set_title(orig.Name.capitalize())
    # plt.show()
    # # endregion

    print(diff)
    print(orig.series[mask])
    assert (orig.all_values[0 : 52 * 7 * 24] == expected[0 : 52 * 7 * 24]).all()
    assert (new.all_values[0 : 52 * 7 * 24] == expected[0 : 52 * 7 * 24]).all()


@pytest.fixture(params=schedules, ids=ids)
def test_schedules(request, run_schedules_idf):
    """Create the test_data"""
    import pandas as pd

    # read original schedule
    idf = schedules_idf()
    schName = request.param
    orig = Schedule(Name=schName, idf=idf)

    print(
        "{name}\tType:{type}\t[{len}]\tValues:{"
        "values}".format(
            name=orig.Name,
            type=orig.schType,
            values=orig.all_values,
            len=len(orig.all_values),
        )
    )

    # create year:week:day version
    new_eps = orig.to_year_week_day()
    new = Schedule(Name=new_eps[0].Name, idf=idf)

    index = orig.series.index
    epv = pd.read_csv(run_schedules_idf)
    epv.columns = epv.columns.str.strip()
    epv = epv.loc[:, schName.upper() + ":Schedule Value [](Hourly)"].values
    expected = pd.Series(epv, index=index)

    print("Year: {}".format(new_eps[0].Name))
    print("Weeks: {}".format([obj.Name for obj in new_eps[1]]))
    print("Days: {}".format([obj.Name for obj in new_eps[2]]))

    yield orig, new, expected


@pytest.fixture(scope="module")
def run_schedules_idf(config):
    files = run_eplus(
        idf_file,
        weather_file="tests/input_data/CAN_PQ_Montreal.Intl.AP" ".716270_CWEC.epw",
        annual=True,
        readvars=True,
        include=["tests/input_data/schedules/TDV_2008_kBtu_CTZ06.csv"],
        return_files=True,
    )
    cache_dir = files[1][0].dirname()
    csv = next(iter(cache_dir.glob("*out.csv")))
    yield csv


def test_ep_versus_schedule(test_schedules):
    """Main test. Will run the idf using EnergyPlus, retrieve the csv file,
    create the schedules and compare"""

    orig, new, expected = test_schedules

    # slice_ = ('2018/01/01 00:00', '2018/01/08 00:00')  # first week
    # slice_ = ('2018/05/20 12:00', '2018/05/22 12:00')
    slice_ = ("2018-10-05 12:00", "2018-10-07 12:00")  # Holiday
    # slice_ = ('2018/01/01 00:00', '2018/12/31 23:00')  # all year
    # slice_ = ('2018/04/30 12:00', '2018/05/01 12:00')  # break

    mask = expected.values.round(3) != orig.all_values.round(3)

    # # region Plot
    # fig, ax = plt.subplots(1, 1, figsize=(5, 4))
    # orig.plot(slice=slice_, ax=ax, legend=True, drawstyle='steps-post',
    #           linestyle='dashed')
    # new.plot(slice=slice_, ax=ax, legend=True, drawstyle='steps-post',
    #          linestyle='dotted')
    # expected.loc[slice_[0]:slice_[1]].plot(label='E+', legend=True, ax=ax,
    #                                        drawstyle='steps-post',
    #                                        linestyle='dashdot')
    # ax.set_title(orig.Name.capitalize())
    # plt.show()
    # # endregion

    print(orig.series[mask])
    assert (
        orig.all_values.round(3)[0 : 52 * 7 * 24] == expected.round(3)[0 : 52 * 7 * 24]
    ).all()
    assert (
        new.all_values.round(3)[0 : 52 * 7 * 24] == expected.round(3)[0 : 52 * 7 * 24]
    ).all()
