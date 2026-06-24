"""Root conftest.py to prevent ROS2 pytest plugin conflicts."""
import sys
import pytest


# Prevent ROS2 pytest plugins from loading by making them unreachable
# This must run before pytest discovers plugins
def pytest_configure(config):
    """Unregister incompatible ROS2 pytest plugins."""
    pm = config.pluginmanager
    # List of problematic plugin names to unregister
    bad_plugins = [
        'launch_testing',
        'launch_testing_ros',
        'ament-lint',
        'ament-copyright',
        'ament-xmllint',
        'ament-pep257',
        'ament-flake8',
    ]
    
    # Try to unregister each plugin
    for name in bad_plugins:
        for plugin_name in [name, name.replace('-', '_')]:
            try:
                pm.unregister(name=plugin_name)
            except (ValueError, AttributeError):
                pass
