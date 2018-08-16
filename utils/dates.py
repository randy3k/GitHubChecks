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

from datetime import datetime

TEN_MINS = 600
ONE_HOUR = 3600
TWO_HOURS = 7200
ONE_DAY = 86400


def fuzzy(event, base=None, date_format=None):
    if not base:
        base = datetime.now()

    if date_format:
        event = datetime.strptime(event, date_format)
    elif type(event) == str:
        event = datetime.fromtimestamp(int(event))
    elif type(event) == int:
        event = datetime.fromtimestamp(event)
    elif type(event) != datetime:
        raise Exception(
            "Cannot convert object `{}` to fuzzy date string".format(event))

    delta = base - event

    if delta.days == 0:
        if delta.seconds < 60:
            return "{} seconds ago".format(delta.seconds)

        elif delta.seconds < 120:
            return "1 min and {} secs ago".format(delta.seconds - 60)

        elif delta.seconds < TEN_MINS:
            return "{} mins and {} secs ago".format(
                delta.seconds // 60,
                delta.seconds % 60)

        elif delta.seconds < ONE_HOUR:
            return "{} minutes ago".format(delta.seconds // 60)

        elif delta.seconds < TWO_HOURS:
            return "1 hour and {} mins ago".format(
                delta.seconds % ONE_HOUR // 60)

        return "over {} hours ago".format(delta.seconds // ONE_HOUR)

    elif delta.days < 2:
        return "over a day ago"

    elif delta.days < 7:
        return "over {} days ago".format(delta.days)

    return "{date:%b} {date.day}, {date.year}".format(date=event)
