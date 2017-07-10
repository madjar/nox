from setuptools import setup

setup(
    setup_requires=['pbr'],
    pbr=True,
    test_suite="nox.tests"
)
