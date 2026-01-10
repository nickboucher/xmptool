from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(name='xmptool',
        version='1.1',
        description='Creates XMP sidecar files to link Live Photos (pairing image and video) and optionally expose hidden or undetectable date/time metadata.',
        long_description=long_description,
        long_description_content_type="text/markdown",
        url='https://github.com/nickboucher/xmptool',
        author='Nicholas Boucher',
        author_email='nicholas.d.boucher+xmptool@gmail.com',
        license='MIT',
        packages=find_packages(),
        entry_points={
            'console_scripts': ['xmptool=xmptool.cli:main'],
        },
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
            "Operating System :: OS Independent",
        ],
        python_requires='>=3.11',
        install_requires=[
            'colorlog>=6.9.0',
            'packaging>=24.2'
        ]
)