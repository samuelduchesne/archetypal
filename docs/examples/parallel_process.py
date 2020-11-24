import pandas as pd
from path import Path

from archetypal import config, parallel_process, IDF

config(cache_folder="../../tests/.temp/cache", use_cache=True, log_console=True)


def main():

    # setup directories and input files
    necb_basedir = Path("../../tests/input_data/trnsys")
    files = necb_basedir.glob("Ref*.idf")
    epw = Path("../../tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw")

    idfs = pd.DataFrame({"file": files, "name": [file.basename() for file in files]})

    # setup the runner. We'll use the DataFrame index as keys (k).
    rundict = {
        k: dict(
            eplus_file=str(file),
            prep_outputs=True,
            weather_file=str(epw),
            expandobjects=True,
            verbose="v",
            design_day=True,
            output_report="sql_file",
        )
        for k, file in idfs.file.to_dict().items()
    }

    sql_files = parallel_process(rundict, IDF, processors=-1, use_kwargs=True)
    return sql_files


if __name__ == "__main__":
    config(use_cache=True, log_console=True)
    sql_files = main()
    print(sql_files)
