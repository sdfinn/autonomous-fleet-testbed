  from setuptools import find_packages, setup

  package_name = 'nav_fleet'

  setup(
      name=package_name,
      version='0.1.0',
      packages=find_packages(exclude=['test']),
      data_files=[
          ('share/ament_index/resource_index/packages',
           ['resource/' + package_name]),
          ('share/' + package_name, ['package.xml']),
          ('share/' + package_name + '/config',
           ['config/nav2_params.yaml', 'config/drift_config.yaml']),
      ],
      install_requires=['setuptools'],
      zip_safe=True,
      maintainer='Mike',
      maintainer_email='sdfinn70@gmail.com',
      description='Fleet navigation test harness',
      license='MIT',
      entry_points={
          'console_scripts': [
              'nav_runner = nav_fleet.nav_runner:main',
              'metrics_collector = nav_fleet.metrics_collector:main',
          ],
      },
  )
