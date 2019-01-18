=====
Usage
=====

To use wado in a project:


.. code-block:: python

    from wado.wado import WadoConnection

    con = WadoConnection(
        hostname="a.wado.server",
        port="80",
        username="testuser",
        password="testpasss"
    )

    con.download_wado_image(
        resource_parameters={"studyInstanceUID": "1.2.3.4", "objectUID": "5.6.7.8"},
        folder="/tmp/wadotest",
    )
