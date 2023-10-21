from setuptools import setup, find_packages

setup(
    name='btc_stamps',
    version='0.1',
    author='Your Name',
    author_email='your.email@example.com',
    description='Bitcoin Stamps Indexing',
    packages=['btc_stamps', 'btc_stamps.transactino_helper', 'btc_stamps.kickstart'],
    # packages=find_packages(),
    install_requires=[
    ],
)