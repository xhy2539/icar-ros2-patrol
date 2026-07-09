from setuptools import setup

package_name = "vision_patrol"

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
    maintainer="Wei Xue",
    maintainer_email="weixue@example.com",
    description="Camera access and vision pipeline nodes for the iCar patrol project.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "fake_camera = vision_patrol.fake_camera_node:main",
            "camera_probe = vision_patrol.camera_probe_node:main",
            "dataset_recorder = vision_patrol.dataset_recorder_node:main",
            "target_tracker = vision_patrol.target_tracker_node:main",
            "vision_node = vision_patrol.vision_node:main",
        ],
    },
)
