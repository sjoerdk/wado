#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `wado` package."""

import pytest

import os
import unittest
import urllib.request, urllib.error, urllib.parse
import logging

from wado.wado import (
    WadoConnection,
    WadoConnectionException,
    WadoConnectionAuthException,
    WadoServerResponseException,
)


from io import BytesIO


def get_mock_response_base(content, url, headers, code):
    """Fake return object for Urllib2.OpenerDirector().open()

    Parameters
    ----------
    content : str
        HTML page content that is being sent back
    url : str
        URL that was being called
    headers : dict
        HTML headers as dict
    code: int
        HTML response code

    Returns
    -------
        urllib2.addinfourl with memory-only open file object containing content

    """
    hdrs = MockHeaders(headers)
    resp = urllib.request.addinfourl(BytesIO(content), hdrs, url)
    resp.code = code
    return resp


def get_mock_response_password_page():
    content = b"<html> \n <description>Login</description>user login at </html>"
    url = "testlogin.com"
    headers = {"Content-Type": "text/html;charset=ISO-8859-1"}
    code = 200
    return get_mock_response_base(content, url, headers, code)


def get_mock_response_wado_object(content=""):
    url = "testlogin.com"
    headers = {
        "Content-Type": "application/dicom",
        "Content-Disposition": "val=test;filename=testfilename.dcm",
    }
    code = 200
    return get_mock_response_base(content, url, headers, code)


def get_server_error():
    hdrs = MockHeaders({})
    url = "testlogin.com"
    code = 500

    resp = urllib.error.HTTPError(url, code, "test server error", hdrs, BytesIO(b""))
    return resp


class MockHeaders(dict):
    """I need to have a httplib.HTTPMessage but this was difficult to
    instantiate. I don't want to make this too difficult. Just mocking
    it with this trashy bare-bones class.

    Python 2.7 has no native mocking lib. Just getting by.

    """

    def getheader(self, key):
        return self.__getitem__(key)


class MockOpenedFile(BytesIO):
    def __init__(self, filename, mode, buf=b""):
        BytesIO.__init__(self, buf)
        self.filename = filename
        self.mode = mode

    def close(self, *args, **kwargs):
        """For testing, just keep these files open"""
        pass


class MockOpenFileManager(object):
    """Dishes out and keeps track of memory-only files

    """

    def __init__(self):
        self.opened = {}

    def open(self, file_path, mode):
        f = MockOpenedFile(file_path, mode)
        self.opened[file_path] = f
        return f


class MockConnectionManager(object):
    """ For mocking Urllib2.OpenerDirector has an open method that returns
    whatever you set for response.

    """

    def __init__(self):
        self.responses = {}
        self.requests = []

    def open(self, url, timeout=0):
        self.requests.append(url)

        return self.responses[url]

    def set_response(self, url, response):
        """Return this response any time open(url) is called

        """
        self.responses[url] = response


class TestWadoConnection(unittest.TestCase):
    root_folder = os.path.dirname(os.path.abspath(__file__))

    def setUp(self):
        hostname = "testhost"
        port = "123"
        user = "testuser"
        password = "testpass"

        # Don't make any actual calls to server
        self.connection_manager = MockConnectionManager()
        self.connection = WadoConnection(hostname, port, user, password)
        self.connection._opener = self.connection_manager

        # Don't make any actual files
        self.open_file_manager = MockOpenFileManager()
        self._org_open = open
        # is this the way to mock the built-in open() inside an object?
        self.connection.open_file = self.open_file_manager.open

        # mock logging so testing does not throw a lot of log lines
        logging.disable(logging.ERROR)

    def test_failing_login(self):
        """If you try to download and keep getting password page, login has failed

        """
        # return password page whenever you call this
        self.connection_manager.set_response(
            "testurl.com", get_mock_response_password_page()
        )

        # if you only get a password page for any url the system must assume
        # login fails
        self.assertRaises(
            WadoConnectionAuthException,
            self.connection.download_image,
            "testurl.com",
            "C:/temp",
        )

    def test_host_not_found(self):
        """If the server is offline or non-existant: informative error


        """

        def failing_call(_, timeout):
            raise urllib.error.URLError("Terrible problems!")

        self.connection_manager.open = failing_call

        # For lower level function stick with built in exceptions
        # Don't want to catch exceptions to early
        self.assertRaises(
            urllib.error.URLError,
            self.connection.download_image,
            "http://test.com",
            "C:/temp",
        )

        # For higher level function re-raise to class exception
        # I want people using higher level functions to get expected exceptions
        self.assertRaises(
            WadoConnectionException,
            self.connection.download_wado_image,
            {"ObjectID": "911"},
            "C:/temp",
        )

    def test_500_server_error_returned(self):
        """If the server is offline or non-existant: informative error


        """

        def failing_call_500(_, timeout=""):
            raise get_server_error()

        self.connection_manager.open = failing_call_500

        # For higher level function re-raise to class exception
        # I want people using higher level functions to get expected exceptions
        self.assertRaises(
            WadoServerResponseException,
            self.connection.download_wado_image,
            {"ObjectID": "911"},
            "C:/temp",
        )

    def test_resource_url(self):
        """ Exposes merge error that gave a lot of headache after a 3-point merge. WADO server will respond with
        403 access denied, while the actual problem was a missing requestType param. This threw me off for a long time.
        making sure this does not happen again.

        """
        resource_parameters = {"studyUID": "123345", "seriesUID": "547567"}
        resource_url = self.connection.get_resource_url(resource_parameters)
        self.assertIn("&requestType=WADO", resource_url)
        self.assertIn("&contentType=application/dicom", resource_url)

    def tearDown(self):
        # Make sure no weird things happen later due to changed built-in
        # methods
        open = self._org_open


if __name__ == "__main__":
    unittest.main()
