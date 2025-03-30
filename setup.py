from setuptools import setup, find_packages

setup(
    name="vmaf_test_app",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "PyQt5>=5.15",
        "opencv-python>=4.5",
        "numpy>=1.21"
    ],
    entry_points={
        'console_scripts': [
            'vmaf-test-app=app.main:main'
        ]
    }
)