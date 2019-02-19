from setuptools import setup

setup(
    name='archetypal',
    version='1.1',
    packages=['archetypal'],
    url='',
    license='MIT License',
    author='Samuel Letellier-Duchesne',
    author_email='samuel.letellier-duchesne@polymtl.ca',
    description='',
    install_requires=['numpy', 'pandas', 'eppy', 'sphinx', 'pycountry',
                      'geopandas', 'shapely', 'osmnx', 'pyproj', 'rasterstats',
                      'pyomo', 'scikit-learn', 'sqlalchemy'],
    test_suite='tests'
)
