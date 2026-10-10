from setuptools import find_packages, setup


package_name = "wafer_cart_core"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", ["config/mission_defaults.yaml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="wafer cart team",
    maintainer_email="wnm0601@users.noreply.github.com",
    description="Hardware-independent mission state machine for the wafer transport cart.",
    license="Proprietary",
    tests_require=["pytest"],
)
