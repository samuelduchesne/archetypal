---
diataxis: tutorial
---

# Your first UMI library

In this tutorial, we will install archetypal 3, download a small office model with the results
of its annual EnergyPlus run, reduce it to a UMI template library, and open that library again
to check what it holds. It takes about ten minutes, most of it for the install.

You need Python 3.10, 3.11 or 3.12, a terminal and an internet connection. You do not need
EnergyPlus: the model comes with its results. The commands are for a Linux or macOS shell; the
two lines that differ on Windows are given where they occur.

## Install archetypal in a new environment

First, make a folder for the tutorial and go into it:

```console
$ mkdir first-umi-library
$ cd first-umi-library
```

Now create a virtual environment and activate it, so that the install leaves the rest of your
system alone:

```console
$ python -m venv .venv
$ source .venv/bin/activate
```

On Windows, activate it with `.venv\Scripts\activate` instead. Notice that the prompt now starts
with `(.venv)`.

archetypal 3 is not on PyPI yet, so we install it from its git repository at the milestone tag
`v3.0.0a1`, together with the fork of epinterface that this tag uses (see
[How to install archetypal 3](../how-to/install.md) for why):

```console
$ pip install "epinterface @ git+https://github.com/samuelduchesne/epinterface@dee8d343eb9aaceb8ae43819ab95232b94fae63a" "archetypal @ git+https://github.com/samuelduchesne/archetypal@v3.0.0a1"
```

pip downloads and builds both packages and their dependencies; this takes a minute or two. Let
us check that the `archetypal` command is there:

```console
$ archetypal --version
```

It prints three lines: the versions of archetypal, idfkit and epinterface. If your shell says
that `archetypal` is not found, the environment is not active: run the activation line again.

## Download the example model, its results and its weather

The example is a three-zone office: two perimeter zones and a core, with office and conference
spaces, each zone served by a packaged terminal air conditioner. Download the model, the
SQLite results of its annual run in Chicago, and the Chicago weather file that run used:

```console
$ curl -LO https://raw.githubusercontent.com/samuelduchesne/archetypal/v3.0.0a1/docs/examples/three_zone.idf
$ curl -LO https://raw.githubusercontent.com/samuelduchesne/archetypal/v3.0.0a1/docs/examples/three_zone.sql
$ curl -LO https://raw.githubusercontent.com/samuelduchesne/archetypal/v3.0.0a1/docs/examples/chicago.epw
```

On Windows, type `curl.exe` instead of `curl`. The folder now holds `three_zone.idf` (about
110 kB), `three_zone.sql` (about 5 MB) and `chicago.epw` (about 1.6 MB).

The model and its results were made for archetypal's tests and are under archetypal's MIT
licence; the weather file is the TMY3 file for Chicago O'Hare that EnergyPlus distributes, in
the public domain.
[`docs/examples/SOURCES.md`](https://github.com/samuelduchesne/archetypal/blob/v3.0.0a1/docs/examples/SOURCES.md)
gives the details. We will not need the weather file today, because the results are already
there; it is what EnergyPlus would need to compute them again.

## Reduce the model to a UMI library

Now reduce the model. We give archetypal the model, its results with `--results`, and the name
of the library to write with `-o`:

<!-- console: exit-status 4 -->
```console
$ archetypal reduce three_zone.idf --results three_zone.sql -o office.json
1 model reduced, 0 failed.
86 losses, 2 approximations reported; see the reports.
Written:
  office.json
Reports:
  office.three_zone.report.json
  office.loss.json
```

The reduction takes a second or two. The summary says that the model was reduced and that
three files were written:

- `office.json` is the UMI template library, with one building template, `three_zone`, whose
  zones are grouped into a core and a perimeter, as UMI expects.
- `office.three_zone.report.json` is the reduction report: which zones went into each group, and
  where every value in the template came from.
- `office.loss.json` is the translation report: what the library could not hold.

Notice the losses. A UMI template is much simpler than an EnergyPlus model, so some detail has
no place in it, and archetypal lists each piece in the reports rather than dropping it silently.
That is also why the command ends with status 4 ("success with losses") rather than 0; the
[command-line reference](../reference/cli.md) lists every status.

## Open the library

Let us check the library by opening it again: `archetypal translate` reads a UMI library and
writes each of its building templates as an SBEM archetype, in the folder we give it with `-o`:

```console
$ archetypal translate office.json -o opened
1 template translated, 0 failed.
0 losses, 0 approximations reported.
Written:
  opened/three_zone.sbem.json
Reports:
  opened/office.loss.json
```

archetypal read the library and found its one building template, `three_zone`. It is now in
`opened/three_zone.sbem.json`, the archetype format that epinterface reads. Nothing was lost on
the way back, so the command ends with status 0, and `opened/office.loss.json` says so.

`office.json` is the file to give UMI: it opens it as a template library and offers
`three_zone` as a building template.

## What we built

We installed archetypal 3, reduced a detailed EnergyPlus model to a UMI template library with
one command, and opened the library again. That is the whole path from a detailed model to a
template that UMI can use.

From here:

- [How to reduce a detailed model to an SBEM archetype](../how-to/reduce-a-model.md) shows the
  layouts, the threshold and the space uses that a reduction can take.
- [How to read a UMI template library into SBEM archetypes](../how-to/read-a-umi-library.md)
  shows how to read the loss report.
- [About reduction](../explanation/reduction.md) explains what an archetype keeps of its model.
