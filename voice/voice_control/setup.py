from setuptools import setup


package_name = "voice_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="xionghaoyu",
    maintainer_email="xionghaoyu@example.com",
    description="MiniCPM-o duplex audio client and ROS2 task router",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "duplex_audio_node = voice_control.duplex_audio_node:main",
            "voice_command_router_node = voice_control.voice_command_router_node:main",
            "doubao_voice_node = voice_control.doubao_voice_node:main",
        ],
    },
)
