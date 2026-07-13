from setuptools import setup

package_name = 'task_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='熊浩宇',
    maintainer_email='xionghaoyu@example.com',
    description='ICAR Patrol - 任务调度核心节点',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'task_manager_node = task_manager.task_manager_node:main',
            'mock_app_node = task_manager.mock_app_node:main',
            'mock_navigation_node = task_manager.mock_navigation_node:main',
            'mock_sensor_node = task_manager.mock_sensor_node:main',
            'mock_vision_node = task_manager.mock_vision_node:main',
            'report_generator_node = task_manager.report_generator_node:main',
            'obstacle_alarm_node = task_manager.obstacle_alarm_node:main',
        ],
    },
)
