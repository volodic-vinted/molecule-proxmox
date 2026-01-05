import setuptools

setuptools.setup(
    name='molecule-proxmox',
    version='1.1.1',
    author='Michael Meffie',
    author_email='mmeffie@sinenomine.net',
    description='Proxmox Molecule Plugin :: run molecule tests using proxmox',
    long_description=open('README.rst').read(),
    long_description_content_type='text/x-rst',
    url='https://github.com/meffie/molecule-proxmox',
    packages=[
        'molecule_proxmox',
        'molecule_proxmox.cookiecutter',
        'molecule_proxmox.modules',
        'molecule_proxmox.playbooks',
        'molecule_proxmox.playbooks.common',
    ],
    package_dir={'': 'src'},
    include_package_data=True,
    entry_points={
        'molecule.driver': [
            'proxmox = molecule_proxmox.driver:Proxmox',
        ],
    },
    install_requires=[
        # molecule plugins are not allowed to mention Ansible as a direct dependency
        'molecule>=6.0.0,<=25.4.0',
        'PyYAML',
        'proxmoxer>=1.3.1',
        'requests',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.10',
)
