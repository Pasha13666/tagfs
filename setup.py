#!/usr/bin/python3.6

from setuptools import setup, find_packages

setup(
    name='tagfs',
    author='Pasha__kun',
    version='1.0.3',
    license='MIT',
    packages=find_packages(),
    install_requires=['fusepy==2.0.4', 'click>=5.1'],
    entry_points={
        'console_scripts': [
            'tagfs = tagfs.__main__:tagfs',
            'mount.tagfs = tagfs.__main__:mount'
        ]
    }
)
