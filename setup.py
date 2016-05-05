#!/usr/bin/env python
# -*- coding: utf8 -*-
from setuptools import setup, find_packages

setup(
    name="Burger",
    packages=find_packages(),
    version="0.3.0",
    description="Extract information from Minecraft bytecode.",
    author="Tyler Kennedy",
    author_email="tk@tkte.ch",
    url="http://github.com/mcdevs/Burger",
    keywords=["java", "minecraft"],
    install_requires=[
        'Jawa'
    ],
    dependency_links=[
        'https://github.com/tktech/Jawa/tarball/master#egg=Jawa'
    ],
    classifiers=[
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Disassemblers"
    ]
)
