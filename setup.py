# To use a consistent encoding
import codecs
import os
import re
import sys
from os import path

# Always prefer setuptools over distutils
from setuptools import find_namespace_packages, setup

here = os.getcwd()

# This check is here if the user does not have a new enough pip to recognize
# the minimum Python requirement in the metadata.
if sys.version_info < (3, 7):
    error = """
archetypal 1.1+ does not support Python 2.x, 3.0, 3.1, 3.2, or 3.3.
Python 3.7 and above is required. This may be due to an out of date pip.
Make sure you have pip >= 9.0.1.
"""
    sys.exit(error)


def read(*parts):
    with codecs.open(path.join(here, *parts), "r") as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


# Get the long description from the README file
with codecs.open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

with open(path.join(here, "requirements.txt")) as f:
    requirements_lines = f.readlines()
install_requires = [r.strip() for r in requirements_lines]

with open(path.join(here, "requirements-dev.txt")) as f:
    requirements_lines = f.readlines()
dev_requires = [r.strip() for r in requirements_lines]

setup(
    name="archetypal",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    packages=find_namespace_packages(
        include=["archetypal", "archetypal.*"], exclude=["tests"]
    ),
    include_package_data=True,
    url="https://github.com/samuelduchesne/archetypal",
    license="MIT License",
    author="Samuel Letellier-Duchesne",
    author_email="samuel.letellier-duchesne@polymtl.ca",
    description="Retrieve, construct, simulate, convert and analyse building archetypes",
    long_description=long_description,
    keywords="Building archetypes",
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require={"dev": dev_requires},
    test_suite="tests",
    entry_points="""
        [console_scripts]
        archetypal=archetypal.cli:cli
    """,
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        "Development Status :: 4 - Beta",
        # Indicate who your project is intended for
        "Intended Audience :: Science/Research",
        # Pick your license as you wish (should match "license" above)
        "License :: OSI Approved :: MIT License",
        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
