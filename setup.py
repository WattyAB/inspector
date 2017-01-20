from __future__ import division, print_function

from setuptools import setup

VERSION = '0.1.1'

import importlib

def raises_importerror(module):
    try:
        importlib.import_module(module)
        return False
    except ImportError:
        return True


def check_if_installed(module, only_if=None, advice='', raise_=False):
    """
    :param module: str, module to try to import or raise if not present
    :param only_if: bool-callback, only raise if true.
    :param advice: str, how to satisfy requirement
    :param raise_: bool, raise or just print warning
    """
    if raises_importerror(module):
        if only_if and only_if():
            # We're good, hopefully the requirement will be satisfied
            # after installation
            return
        txt = "Missing extra dependency '{}'. {}".format(module, advice)
        if raise_:
            raise ImportError(txt)
        else:
            print('WARNING: %s' %txt)
    else:
        print("{} installed - OK!".format(module))


pre_dependencies = [
    {
        'module': 'PyQt4',
        'advice': "Try e.g. 'apt-get install python-qt4'",
    },
    {
        'module': 'matplotlib.backends.backend_qt4agg',
        'only_if': lambda: raises_importerror('matplotlib'),
        'advice': 'Try reinstalling matplotlib',
    }
]

from setuptools.command.install import install
from setuptools.command.develop import develop

class PreInstallHook(install):
    def run(self):
        [check_if_installed(**dep_dict) for dep_dict in pre_dependencies]
        install.run(self)


class PreDevelopHook(develop):
    def run(self):
        [check_if_installed(**dep_dict) for dep_dict in pre_dependencies]
        develop.run(self)


setup(
    name="inspector",
    version=VERSION,
    description='Tool for easy plotting of 1-dimensional data, '
                'built on PyQt and matplotlib',
    url='https://github.com/WattyAB/inspector',
    author='Lennart Liberg, Watty AB',
    license='Apache License 2.0',
    packages=[
        'inspector'
    ],
    install_requires=[
        'pandas>=0.17.0',
        'numpy>=1.9.0',
        'matplotlib>=1.4.2,<2.0.0',
        'mock',
    ],
    extras_require={
        'test': [
            'nose',
        ],
        'unpackers': [  # subject to change / move. Listed here in mean time.
            'lz4',
            'msgpack-python'
        ]
    },
    cmdclass={
        'install': PreInstallHook,
        'develop': PreDevelopHook,
    },
    entry_points={
        'console_scripts': [
            'inspector=inspector.main:main',
        ],
    },
)
