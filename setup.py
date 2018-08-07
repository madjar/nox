from setuptools import setup

setup(
    setup_requires=['pbr'],
    pbr=True,
    package_data={'': ['enumerate_tests.nix']},
    include_package_data=True,
    test_suite="nox.tests"
)
