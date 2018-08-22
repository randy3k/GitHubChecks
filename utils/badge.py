import threading
from collections import defaultdict


class DynamicBadge:
    dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    message = None
    thread = None

    def __init__(self, view, name):
        self.view = view
        self.name = name

    def stop(self):
        if self.thread:
            self.thread.cancel()

    def erase(self):
        self.stop()
        self.view.erase_status(self.name)

    def set_status(self, message):
        self.message = message
        self.stop()
        self.update()

    def update(self, status=0):
        if not self.message:
            return
        status = status % 10
        self.view.set_status(
            self.name,
            self.message.format_map(defaultdict(str, indicator=self.dots[status])))

        if "{indicator}" in self.message:
            self.thread = threading.Timer(0.1, lambda: self.update(status+1))
            self.thread.start()

    def __del__(self):
        self.erase()
