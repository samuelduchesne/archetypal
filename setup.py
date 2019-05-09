# To use a consistent encoding
import codecs
import re
import sys
from os import path

# Always prefer setuptools over distutils
from setuptools import setup

here = path.abspath(path.dirname(__file__))

# This check is here if the user does not have a new enough pip to recognize
# the minimum Python requirement in the metadata.
if sys.version_info < (3, 6):
    error = """
archetypal 1.1+ does not support Python 2.x, 3.0, 3.1, 3.2, or 3.3.
Python 3.6 and above is required. This may be due to an out of date pip.
Make sure you have pip >= 9.0.1.
"""
    sys.exit(error)


def read(*parts):
    with codecs.open(path.join(here, *parts), 'r') as fp:
        return fp.read()


def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


# Get the long description from the README file
with codecs.open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

with open('requirements.txt') as f:
    requirements_lines = f.readlines()
install_requires = [r.strip() for r in requirements_lines]

setup(
    name='archetypal',
    version=find_version('archetypal', '__init__.py'),
    packages=['archetypal'],
    url='https://github.com/samuelduchesne/archetypal',
    license='MIT License',
    author='Samuel Letellier-Duchesne',
    author_email='samuel.letellier-duchesne@polymtl.ca',
    description='',
    long_description=long_description,
    keywords='Building archetypes',
    python_requires='>=3.6',
    install_requires=install_requires,
    extras_require={'dev': [],
                    'tests': ['coverage', 'coveralls', 'pytest', 'matplotlib'],
                    'docs': ['sphinx', 'nbsphinx', 'jupyter_client',
                             'ipykernel']},
    test_suite='tests'
)
