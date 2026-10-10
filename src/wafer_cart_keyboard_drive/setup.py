from setuptools import find_packages, setup


package_name = "wafer_cart_keyboard_drive"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["pynput", "pyserial", "setuptools"],
    zip_safe=True,
    maintainer="wafer cart team",
    maintainer_email="wnm0601@users.noreply.github.com",
    description="Standalone Windows keyboard driving beta with dry-run safety.",
    license="Proprietary",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "keyboard_drive = wafer_cart_keyboard_drive.cli:main",
        ],
    },
)
