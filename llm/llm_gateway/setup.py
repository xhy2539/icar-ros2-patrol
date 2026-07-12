from setuptools import setup

package_name = "llm_gateway"

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
    maintainer_email="xionghaoyu@example.com",
    description="LLM gateway for natural-language task parsing and patrol reports.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "llm_gateway_node = llm_gateway.llm_gateway_node:main",
        ],
    },
)
