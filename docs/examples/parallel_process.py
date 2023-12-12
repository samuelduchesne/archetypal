import pandas as pd
from path import Path

from archetypal.idfclass.idf import IDF
from archetypal.utils import config, parallel_process

config(cache_folder="../../tests/.temp/cache", log_console=True)


def main():

    # setup directories and input files
    necb_basedir = Path("../../tests/input_data/necb")
    files = necb_basedir.glob("Ref*.idf")
    epw = Path("../../tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw")

    idfs = pd.DataFrame({"file": files, "name": [file.basename() for file in files]})

    # setup the runner. We'll use the DataFrame index as keys (k).
    rundict = {
        k: dict(
            eplus_file=str(file),
            prep_outputs=True,
            epw=str(epw),
            expandobjects=False,
            verbose="v",
            design_day=True,
        )
        for k, file in idfs.file.to_dict().items()
    }

    def load_and_simulate(**kwargs):
        """Load IDF model, simulate, and return sql_file path."""
        return IDF(**kwargs).simulate().sql_file

    idfs = parallel_process(rundict, load_and_simulate, processors=-1, use_kwargs=True)
    return idfs


if __name__ == "__main__":
    config(log_console=True)
    idfs = main()
    print(idfs)
