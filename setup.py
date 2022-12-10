"""A setuptools based setup module.

See:
https://packaging.python.org/guides/distributing-packages-using-setuptools/
https://github.com/pypa/sampleproject
"""

from setuptools import setup
import pathlib

here = pathlib.Path(__file__).parent.resolve()

# Get the long description from the README file
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="audite",
    version="0.4.5",
    description="Instant data auditing for SQLite",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/chrisfrank/audite",
    author="Chris Frank",
    classifiers=[  # Optional
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        "Development Status :: 3 - Alpha",
        # Indicate who your project is intended for
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3 :: Only",
    ],
    keywords="sqlite, audit, history, change-data-capture, change feed",
    packages=["audite"],
    install_requires=[],
    python_requires=">=3.7, <4",
    entry_points={
        "console_scripts": ["audite=audite.__main__:main"],
    },
    project_urls={
        "Bug Reports": "https://github.com/chrisfrank/audite",
        "Source": "https://github.com/chrisfrank/audite",
    },
)
