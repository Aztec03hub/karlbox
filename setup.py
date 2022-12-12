from setuptools import find_packages, setup

setup(
    name='OmronVTInterfaceModule',
    version='0.8.1',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'flask',
        'flask_socketio',
        'pyserial',
    ],
)