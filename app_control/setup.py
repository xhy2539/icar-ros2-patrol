from setuptools import find_packages, setup


package_name = "app_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/app_control"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="icar team",
    maintainer_email="xhy2539@example.com",
    description="Safe app control bridge and velocity mux",
    license="MIT",
    entry_points={
        "console_scripts": [
            "app_bridge_node = app_control.app_bridge_node:main",
            "velocity_mux_node = app_control.velocity_mux_node:main",
        ]
    },
)
