from setuptools import setup

package_name = "cloud_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="熊浩宇",
    maintainer_email="xionghaoyu@icar.com",
    description="iCar MQTT cloud bridge — connects ROS2 to cloud MQTT broker",
    license="Apache License 2.0",
    entry_points={
        "console_scripts": [
            "cloud_bridge_node = cloud_bridge.cloud_bridge_node:main",
        ],
    },
)
