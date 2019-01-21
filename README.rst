====
wado
====


.. image:: https://img.shields.io/pypi/v/wado.svg
        :target: https://pypi.python.org/pypi/wado

.. image:: https://img.shields.io/travis/sjoerdk/wado.svg
        :target: https://travis-ci.org/sjoerdk/wado

.. image:: https://readthedocs.org/projects/wado/badge/?version=latest
        :target: https://wado.readthedocs.io/en/latest/?badge=latest
        :alt: Documentation Status

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/ambv/black


DICOM WADO file download


* Free software: GNU General Public License v3
* Documentation: https://wado.readthedocs.io.


Features
--------

* Download DICOM files via http with the WADO protocol

Disclaimers
-----------
* Has only been tested live on AGFA Enterprise Imaging VNA 8. Different servers might have slightly different implementations of the WADO protocol. If you are working with a different pacs, please consider (see section :ref:`Contributing` ).

* WADO only. Does not support DICOM C-ECHO, C-STORE etc.. For other protocols see the excellent `pynetdicom lib <https://pypi.org/project/pynetdicom/>`_

Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.

.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
