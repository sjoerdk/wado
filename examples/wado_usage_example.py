"""Minimal example of how to download an object using WADO

This assumes you already know the studyInstanceUID and ObjectUID
"""

from wado.wado import WadoConnection

con = WadoConnection(
    hostname="a.wado.server", port="80", username="testuser", password="testpasss"
)

con.download_wado_image(
    resource_parameters={"studyInstanceUID": "1.2.3.4", "objectUID": "5.6.7.8"},
    folder="/tmp/wadotest",
)
