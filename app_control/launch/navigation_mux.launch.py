"""Launch vendor Nav2 with every velocity command routed through velocity_mux."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetRemap


def generate_launch_description():
    nav_package_dir = get_package_share_directory("yahboomcar_nav")
    nav2_bringup_dir = get_package_share_directory("nav2_bringup")

    use_sim_time = LaunchConfiguration("use_sim_time")
    map_yaml_path = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument(
                "map",
                default_value=os.path.join(nav_package_dir, "maps", "yahboomcar.yaml"),
            ),
            DeclareLaunchArgument(
                "params_file",
                default_value=os.path.join(
                    nav_package_dir, "params", "dwa_nav_params.yaml"
                ),
            ),
            GroupAction(
                [
                    SetRemap(src="/cmd_vel", dst="/cmd_vel_nav"),
                    IncludeLaunchDescription(
                        PythonLaunchDescriptionSource(
                            [nav2_bringup_dir, "/launch", "/bringup_launch.py"]
                        ),
                        launch_arguments={
                            "map": map_yaml_path,
                            "use_sim_time": use_sim_time,
                            "params_file": params_file,
                        }.items(),
                    ),
                    Node(
                        package="app_control",
                        executable="nav2_goal_adapter_node",
                        output="screen",
                    ),
                ]
            ),
        ]
    )
