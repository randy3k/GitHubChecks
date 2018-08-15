"""
A simple HTTP interface for making GET, PUT and POST requests. (copy from GitSavvy)

The MIT License (MIT)

Copyright (c) 2015 Dale Bustad <dale@divmain.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import http.client
import json
from urllib.parse import urlparse
from base64 import b64encode
from functools import partial
from collections import namedtuple

Response = namedtuple("Response", ("payload", "headers", "status", "is_json"))


def request(verb, host, port, path, payload=None, https=False, headers=None, auth=None,
            redirect=True):
    """
    Make an HTTP(S) request with the provided HTTP verb, host FQDN, port number, path,
    payload, protocol, headers, and auth information.  Return a response object with
    payload, headers, JSON flag, and HTTP status number.
    """
    headers = {}
    headers["User-Agent"] = "GitHubBuildStatus Sublime Plug-in"

    if auth:
        # use basic authentication
        username_password = "{}:{}".format(*auth).encode("ascii")
        headers["Authorization"] = "Basic {}".format(b64encode(username_password).decode("ascii"))

    connection = (http.client.HTTPSConnection(host, port)
                  if https
                  else http.client.HTTPConnection(host, port))
    connection.request(verb, path, body=payload, headers=headers)

    response = connection.getresponse()
    response_payload = response.read()
    response_headers = dict(response.getheaders())
    status = response.status

    is_json = "application/json" in response_headers["Content-Type"]
    if is_json:
        response_payload = json.loads(response_payload.decode("utf-8"))

    response.close()
    connection.close()

    if redirect and verb == "GET" and status == 301 or status == 302:
        return request_url(
            verb,
            response_headers["Location"],
            headers=headers,
            auth=auth
        )

    return Response(response_payload, response_headers, status, is_json)


def request_url(verb, url, payload=None, headers=None, auth=None):
    parsed = urlparse(url)
    https = parsed.scheme == "https"
    return request(
        verb,
        parsed.hostname,
        parsed.port or 443 if https else 80,
        parsed.path,
        payload=payload,
        https=https,
        headers=headers,
        auth=([parsed.username, parsed.password]
              if parsed.username and parsed.password
              else None)
    )


get = partial(request, "GET")
post = partial(request, "POST")
put = partial(request, "PUT")

get_url = partial(request_url, "GET")
post_url = partial(request_url, "POST")
put_url = partial(request_url, "PUT")
