# -*- coding: utf-8 -*-

"""Download dicom from a WADO server.

This module wraps HTML calls to a WADO-enabled  server in a python-friendly way
WADO (Web Access to dicom Persistent Object) is a standard for retrieving dicom
via HTML calls

see http://dicom.nema.org/dicom/2004/04_18PU.PDF
"""

import cgi
import os
import logging
import urllib
import socket

from threading import RLock

import urllib.request
import urllib.parse
import urllib.error

try:
    import cookielib
except ImportError:
    import http.cookiejar as cookielib

logger = logging.getLogger("wado")


class WadoConnection(object):
    """Represents a connection to a WADO server

    Tries to translate the server responses to useful python events
    """

    def __init__(self, hostname, port, username, password, force_transfer_syntax=None):
        """

        Parameters
        ----------
        hostname: str
            hostname of WADO server including http://
        port: str
            port to talk to WADO server
        username: str
            username to use
        password: str
            password to use
        force_transfer_syntax: str, optional
            If given, append transferSyntax=this to any WADO download link. A list of transferSyntaxes can be found at
            https://www.dicomlibrary.com/dicom/transfer-syntax/, If not given, whatever is the default for the server
            will be used.

        """
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.force_transfer_syntax = force_transfer_syntax
        self._opener = None

        self.__lock = RLock()

    def __repr__(self, *args, **kwargs):
        desc = ("WadoConnection {id} for {host}:{port} (username '{user}')" "").format(
            id=id(self), host=self.hostname, port=self.port, user=self.username
        )
        return desc

    @property
    def opener(self):
        if not self._opener:
            cj = cookielib.CookieJar()
            self._opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(cj)
            )

        return self._opener

    def get_base_url_for_query(self):
        """Return url to the WADO server up to and including the ?"""
        base = "http://{host}:{port}/wado/?".format(host=self.hostname, port=self.port)
        return base

    def get_resource_url(self, resource_parameters):
        """Generate url to get a dicom resource with the given parameters

        parameters
        ----------
        resource_parameters : dict
            like {"studyUID" : "123345", "seriesUID" : "547567"}
        """

        request = self.get_base_url_for_query()
        if resource_parameters:
            request += urllib.parse.urlencode(resource_parameters)
            request += "&contentType=application/dicom&requestType=WADO"
        if self.force_transfer_syntax:
            request += f"&transferSyntax={self.force_transfer_syntax}"
        return request

    def get_login_url(self):
        """Loading this url should log in to the WADO server

        """
        loginurl = (
            "http://{host}:{port}/wado/j_security_check?"
            "j_username={user}&j_password={passwd}"
            ""
        ).format(
            host=self.hostname, port=self.port, user=self.username, passwd=self.password
        )

        return loginurl

    def get_response_top_level(self, resource_url):
        """Download WADO resource given by URL

        parameters
        ----------
        resource_url : str
            full url to resource


        Returns
        -------
        string
            urllib2.addinfourl


        Raises
        ------
        WadoConnectionAuthException
            if credentials are not working
        WadoWrapperException
            if anything else goes wrong during download

        Note
        ----
        Something rather confusing is going on here. To authenticate, you
        cannot load the password url directly, because it will give you a
        208 timeout error. The only way to get the login cookie and the
        file you want is this:
        * request an actual WADO resource, this is then rejected because no
          password
        * new send an empty request which sends password and username only.
        * The password request, without any resource identifier
          now returns all of the data that should have been returned by the
          original request.
        * Subsequently, any resource can be requested without this password
          strangeness.

        """

        try:
            # download this resource
            resp = self.get_response_safe(resource_url)
        except WadoConnectionAuthException:
            # authentication failed. Try to log in. Image data is returned from
            # (see note in method description)
            try:
                resp = self.get_response_safe(self.get_login_url())
            except WadoConnectionAuthException:
                # re-raise to make message a bit more informative
                msg = "Credentials for user '{0}' do not seem to be" " accepted".format(
                    self.username
                )
                raise WadoConnectionAuthException(msg)
            except WadoServerResponseException as e:
                # re-raise to make message a bit more informative"
                msg = (
                    "got some response but not HTML from WADO server at"
                    "'{0}:{1}'. Maybe wrong port or hostname."
                    " Original error:'{2}'".format(self.hostname, self.port, str(e))
                )
                raise WadoConnectionException(msg)
            # In case server returned a page but then broke, or resource not
            # found
            except urllib.error.URLError as e:
                self.handle_urlerror(e, resource_url)
        # In case the whole server does not respond
        except urllib.error.URLError as e:
            self.handle_urlerror(e, resource_url)

        return resp

    def download_wado_image(self, resource_parameters, folder):
        """Download the DICOM given by resource_parameters to filename

        parameters
        ----------
        resource_parameters : dict
            download the resource corresponding to these parameters
            like {"studyUID" : "123345", "seriesUID" : "547567"}
        folder : str
            download to this path

        Returns
        -------
        string
            the filename+extension that the  download was written to

        Raises
        ------
        WadoConnectionAuthException
            if credentials are not working
        WadoWrapperException
            if anything else goes wrong during download

        """

        with self.__lock:
            resource_url = self.get_resource_url(resource_parameters)

            resp = self.get_response_top_level(resource_url)

            # check whether the response can be written to file
            file_name = resp.get_filename()
            if not file_name:
                msg = (
                    "This url does not specify a filename."
                    "I don't know which name to use to save this"
                )
                raise WadoConnectionException(msg)
            if not resp.is_image_data:
                msg = "This url does seem to yield any image data"
                raise WadoConnectionException(msg)

            file_path = os.path.join(folder, file_name)
            self.write_response(resp, file_path)

    def handle_urlerror(self, e, resource_url):
        """Handles errors coming from urllib2. Recasts to WadoWrapperExceptions

        and adds useful context info.
        """
        if isinstance(e, urllib.error.HTTPError):
            if e.code == 500:
                msg = (
                    "Got 'server error' response when requesting '{0}:"
                    " This might happen if you do not include seriesUID"
                    " explicitly. Original "
                    "error:'{1}'"
                ).format(str(resource_url), str(e))
                raise WadoServerResponseException(msg, e)
            elif e.code == 403:
                msg = (
                    "Got '403, access denied' response when requesting '{0}:"
                    " Something might be wrong with your credentials"
                    "error:'{1}'"
                ).format(str(resource_url), str(e))
                raise WadoServerResponseException(msg, e)
            else:
                msg = (
                    "Got HTTP error response from server when requesting"
                    " '{0}' Original error:'{1}'"
                    ""
                ).format(str(resource_url), str(e))
                raise WadoServerResponseException(msg, e)

        if e.reason == "Not Found":
            msg = ("WADO resource for '{0}' not found").format(str(resource_url))
            raise WadoResourceNotFoundException(msg)
        else:
            msg = (
                "Did not get response from WADO server at '{0}:{1}'"
                ". Original error:'{2}'"
            ).format(self.hostname, self.port, str(e))
            raise WadoConnectionException(msg)

    def get_response_raw(self, url):
        """Query this url, return response unprocesed.

        The wrapping makes it easier to work with in this context;
        hides lots of HTML header details.

        Parameters
        ----------
        url : str
            call this url

        Returns
        -------
        :obj:urllib2.addinfourl:
            what comes out of urllib2.open()

        raises
        ------
        urllib2.URLError
            when url cannot be opened or returns 404

        """
        timeouts_series = [30, 30, 30, 300]

        with self.__lock:
            self.mylog("Opening {0}".format(url), logging.DEBUG)

            for timeout_i, timeout in enumerate(timeouts_series):

                try:
                    u = self.opener.open(url, timeout=timeout)
                except socket.timeout as e:
                    if timeout_i >= len(timeouts_series):
                        raise e
                else:
                    if u.getcode() == 200:
                        break
            return u

    def get_response(self, url):
        """Query this url, return response as wrapped class

        The wrapping makes it easier to work with in this context;
        hides lots of HTML header details.

        Parameters
        ----------
        url : str
            call this url

        Returns
        -------
        :obj:WadoServerResponse
            The response from querying this url

        raises
        ------
        urllib2.URLError
            when url cannot be opened or returns 404

        """
        with self.__lock:
            u = self.get_response_raw(url)
            resp = WadoServerResponse(u)
            return resp

    def mylog(self, msg, loglevel=logging.INFO):
        sm = self.make_safe_for_logging(msg)
        if loglevel == logging.DEBUG:
            logger.debug(sm)
        elif loglevel == logging.INFO:
            logger.info(sm)
        elif loglevel == logging.WARNING:
            logger.warn(sm)
        elif loglevel == logging.ERROR:
            logger.error(msg)(sm)
        elif loglevel == logging.CRITICAL:
            logging.critical(sm)
        else:
            raise ValueError("unknown loglevel '{0}'".format(loglevel))

    def make_safe_for_logging(self, msg):
        """ Don't write passwords to log.

        """
        return msg.replace(self.password, "<password>")

    def open_file(self, file_path, mode):
        """ Override this in tests
        """
        return open(file_path, mode)

    def get_response_safe(self, url):
        """Get response from server, check for common problems

        Parameters
        ----------
        url : string
            Download from this location

        Raises
        ------
        WadoConnectionException
            When authentication fails url does not yield dicom data to download
        """
        with self.__lock:
            resp = self.get_response(url)
            if resp.is_password_request_page:
                msg = "Not authenticated. I'm receiving a login page"
                raise WadoConnectionAuthException(msg)
            return resp

    def write_response(self, resp, file_path):
        """Write this response to file in a buffered way"""

        f = self.open_file(file_path, "wb")
        block_sz = 8192
        while True:
            filebuffer = resp.addinfourl.read(block_sz)
            if not filebuffer:
                break
            f.write(filebuffer)

        f.close()

    def download_image(self, url, folder):
        """Download dicom from from url and save to file.

        Downloads in chunks so should be able to handle large files without
        memory problems.
        Based on script by http://stackoverflow.com/users/394/pablog


        Parameters
        ----------
        url : string
            Download from this location
        folder : string
            Download to this folder

        Raises
        ------
        WadoConnectionException
            When url does not yield dicom data to download
        """
        with self.__lock:
            resp = self.get_response_safe(url)

            # check whether the response can be written to file
            file_name = resp.get_filename()
            if not file_name:
                msg = (
                    "This url does not specify a filename."
                    "I don't know which name to use to save this"
                )
                raise WadoConnectionException(msg)
            if not resp.is_image_data:
                msg = "This url does seem to yield any image data"
                raise WadoConnectionException(msg)

            file_path = os.path.join(folder, file_name)
            self.write_response(resp, file_path)


class WadoServerResponseType(object):
    """These types of responses can be returned by the WADO server

    """

    PASSWORD_REQUEST_PAGE = "password_request_page"
    DICOM_DATA = "dicom_data"
    ERROR = "error"
    UNKNOWN = "unknown"


class DICOMTransferSyntax:
    """Transfer syntaxes from https://www.dicomlibrary.com/dicom/transfer-syntax/"""

    IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
    EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"


class WadoServerResponse(object):
    """Response being sent back from the WADO server.

    What is the server saying? Did it work? Wrong password? down for
    maintenance? Here is the dicom file? This class tries to find out.

    Parameters
    ----------
    addinfourl : :obj:`urlliub.addinfourl`
        object containing open file and response information

    Note
    ----
    This class is tailored to responses given by the "AGFA Enterprise Imaging VNA 8.0.0".
    It might not work properly for different types of WADO server

    """

    server_type = "AGFA Enterprise Imaging VNA 8.0.0"

    def __init__(self, addinfourl):
        self.addinfourl = addinfourl
        self._text = None

    @property
    def is_password_request_page(self):
        """ Is this the page where a password is requested?

        """
        if self.is_text_response:
            return "user login at" in self.text.decode("utf-8").lower()
        else:
            # Don't read something that might be a huge download. Will drain
            # memory
            return False

    @property
    def is_text_response(self):
        h = self.addinfourl.headers
        if hasattr(h, "getheader"):
            ct = h.getheader("Content-Type")
        else:
            ct = h["Content-Type"]
        if ct is None:
            # no content-type means super weird response. Definitely wrong
            # stuff
            msg = "No content-type specified for this response"
            raise WadoServerResponseException(msg)

        return "text/html" in ct

    @property
    def is_image_data(self):
        """Is the server sending back dicom or JPEG data with this response?

        """
        image_content_types = ["image/jpeg", "image/gif", "image/bmp", "image/tiff"]

        h = self.addinfourl.headers
        if hasattr(h, "getheader"):
            is_dicom = h.getheader("Content-Type") == "application/dicom"
            is_image = h.getheader("Content-Type") in image_content_types
        else:
            is_dicom = h["Content-Type"] == "application/dicom"
            is_image = h["Content-Type"] in image_content_types

        return is_dicom or is_image

    @property
    def text(self):
        """Return text contained in this response. Cache content because
        default socket._fileobject can only be read once.

        """
        if self._text:
            return self._text
        elif self.is_text_response:
            self._text = self.addinfourl.read()
        return self._text

    def get_filename(self):
        """Return the filename that is given with this response.

        Returns None if no filename is given
        """

        cd = self.addinfourl.headers.get("Content-Disposition")
        if cd:
            return cgi.parse_header(cd)[1]["filename"]
        else:
            return None

    def get_response_type(self):
        """What type of response is this?

        """
        if self.is_password_request_page:
            return WadoServerResponseType.PASSWORD_REQUEST_PAGE
        elif self.is_image_data():
            return WadoServerResponseType.DICOM_DATA
        else:
            return WadoServerResponseType.UNKNOWN


class WadoWrapperException(Exception):
    pass


class WadoServerResponseException(WadoWrapperException):
    """Server response is something I can't understand. Keep complete original
    exception

    """

    def __init__(self, msg, org_exception=None):
        super(WadoServerResponseException, self).__init__(msg)
        self.org_exception = org_exception


class WadoResourceNotFoundException(WadoWrapperException):
    pass


class WadoConnectionException(WadoWrapperException):
    pass


class WadoConnectionAuthException(WadoConnectionException):
    pass
