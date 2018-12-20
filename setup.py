from setuptools import setup

setup(
    name='pyumi',
    version='1.0',
    packages=['pyumi', 'pyumi.tests'],
    url='',
    license='MIT License',
    author='Samuel Letellier-Duchesne',
    author_email='samuel.letellier-duchesne@polymtl.ca',
    description='',
    install_requires=['numpy', 'pandas', 'eppy', 'sphinx'],
    test_suite='tests'
)
