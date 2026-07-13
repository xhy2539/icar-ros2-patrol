from setuptools import setup, find_packages

package_name = 'navigation'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    py_modules=['navigation_utils'],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='曹莹',
    maintainer_email='caoying@example.com',
    description='ICAR Patrol - 导航模块',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'navigation_node = navigation.navigation_node:main',
            'patrol_node = navigation.patrol_node:main',
            'obstacle_avoid_node = obstacle_avoid.obstacle_avoid_node:main',
            'slam_node = slam.slam_node:main',
            'lidar_node = lidar.lidar_node:main',
        ],
    },
)
