import os.path

import setuptools


current_directory = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(current_directory, "README.md"), encoding="utf-8") as h:
    long_description = h.read()

with open(os.path.join(current_directory, "requirements.txt")) as h:
    install_requires = h.read().split("\n")

package_name = "ctf_builder"

setuptools.setup(
    name=package_name,
    version="0.0.23",
    license="MIT",
    author="Alexandre Lavoie",
    author_email="alexandre.lavoie00@gmail.com",
    description="Tool for building CTFs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/alexandre-lavoie/ctf-builder",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=install_requires,
    entry_points={
        "console_scripts": [
            f"ctf={package_name}.cli:cli",
        ],
    },
)
