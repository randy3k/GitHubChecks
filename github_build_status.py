import sublime
import sublime_plugin
import subprocess
import threading
from datetime import datetime
import time
import os
import socket
import webbrowser

from .utils import dates
from .query.github import query_github, parse_remote_url


URL_POPUP = """
<style>
body {
    margin: 0px;
}
div {
    border: 1px;
    border-style: solid;
    border-color: grey;
}
</style>
<body>
<div>
<a href="open">
<img width="20%" height="20%" src="res://Packages/GitHubBuildStatus/images/link.png" />
</a>
</div>
</body>
"""


def plugin_loaded():
    pass


def plugin_unloaded():
    pass


def parse_time(time_string):
    return datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")


class GitCommand:

    def gbs_settings(self, key, default=None):
        s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
        return s.get(key, default)

    def git(self, cmd, cwd=None):
        plat = sublime.platform()
        if not cwd:
            cwd = self.getcwd()
        if not cwd or not os.path.isdir(cwd):
            return

        if type(cmd) == str:
            cmd = [cmd]
        cmd = [self.gbs_settings("git", "git")] + cmd
        if plat == "windows":
            # make sure console does not come up
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 cwd=cwd, startupinfo=startupinfo)
        else:
            my_env = os.environ.copy()
            my_env["PATH"] = "/usr/local/bin:/usr/bin:" + my_env["PATH"]
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 cwd=cwd, env=my_env)
        p.wait()
        stdoutdata, stderrdata = p.communicate()
        stdout = stdoutdata.decode('utf-8')
        if stdout:
            stdout = stdout.strip()
        return stdout

    def getcwd(self):
        if hasattr(self, "view"):
            view = self.view
            window = view.window()
        else:
            window = self.window
            view = window.active_view()

        f = view.file_name() if view else None
        cwd = None
        if f:
            cwd = os.path.dirname(f)
        if not cwd:
            if window and window.folders():
                cwd = window.folders()[0]
        return cwd

    def branch(self):
        return self.git(["symbolic-ref", "HEAD", "--short"])


builds = {}


class GbsFetchCommand(GitCommand, sublime_plugin.WindowCommand):
    thread = None
    last_fetch_time = 0
    _branch = None
    folders = None

    def run(self, force=False, verbose=False):
        window = self.window
        if self.folders and self.folders != window.folders():
            force = True

        branch = self.branch()
        if self._branch and self._branch != branch:
            force = True

        if not branch:
            if verbose or self.gbs_settings("debug", False):
                print("branch not found")
            return

        if not force and time.time() - self.last_fetch_time < self.gbs_settings("cooldown", {}):
            return

        if time.time() - self.last_fetch_time < 1:
            # still, avoid too frequent refresh
            return

        self.folders = window.folders()
        self.last_fetch_time = time.time()
        self._branch = branch

        if force and self.thread:
            self.thread.cancel()
            self.thread = None

        if not self.thread:
            sublime.set_timeout_async(lambda: self.run_async(force, verbose))

    def run_async(self, force=False, verbose=False):

        window = self.window
        if not window:
            return

        debug = self.gbs_settings("debug", False)

        remote = self.git(["config", "branch.{}.remote".format(self._branch)])
        if not remote:
            if verbose or debug:
                print("remote not found")
            return
        remote_url = self.git(["config", "remote.{}.url".format(remote)])
        if not remote_url:
            return
        tracking_branch = self.git(["config", "branch.{}.merge".format(self._branch)])
        if not tracking_branch or not tracking_branch.startswith("refs/heads/"):
            return
        tracking_branch = tracking_branch.replace("refs/heads/", "")

        token = self.gbs_settings("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None

        path = "/repos/{owner}/{repo}/statuses/{branch}".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            branch=tracking_branch
        )

        if debug:
            print("fetching from github api: {}/{}".format(github_repo.owner, github_repo.repo))
        try:
            reponse = query_github(path, github_repo, token)
        except socket.gaierror:
            if verbose or debug:
                print("network error")
            return

        contexts = {}
        if reponse.status == 200 and reponse.is_json:
            for status in reponse.payload:
                context = status["context"]
                if context not in contexts or \
                        parse_time(status["updated_at"]) >  \
                        parse_time(contexts[context]["updated_at"]):
                    contexts[context] = {
                        "state": status["state"],
                        "description": status["description"],
                        "target_url": status["target_url"],
                        "created_at": status["created_at"],
                        "updated_at": status["updated_at"]
                    }
        else:
            if verbose or debug:
                print("request status: {:d}".format(reponse.status))
                if debug:
                    print(reponse.payload)
            return

        if "github/pages" in contexts:
            del contexts["github/pages"]

        builds[window.id()] = {
            "contexts": contexts
        }
        pending = sum(status["state"] == "pending" for status in contexts.values())

        if contexts and pending:
            self.thread = threading.Timer(
                int(self.gbs_settings("refresh", {})),
                lambda: window.run_command("gbs_update", {"force": True}))
            self.thread.start()

        view = window.active_view()
        if view:
            view.run_command("gbs_render")

        if verbose:
            window.status_message("GitHub build status refreshed.")


class GbsRenderCommand(sublime_plugin.TextCommand):

    build = None

    def run(self, _):
        sublime.set_timeout_async(lambda: self.run_async())

    def run_async(self):
        view = self.view
        window = view.window()
        if not window:
            return
        if window.id() not in builds:
            return

        build = builds[window.id()]
        if build == self.build:
            return
        self.build = build

        contexts = build["contexts"]
        success = sum(status["state"] == "success" for status in contexts.values())
        failure = sum(status["state"] == "failure" for status in contexts.values())
        error = sum(status["state"] == "error" for status in contexts.values())
        pending = sum(status["state"] == "pending" for status in contexts.values())
        total = success + failure + error + pending

        self.update_output_panel(contexts, success, failure, error, pending)

        if pending:
            message = "Build {:d}({:d})/{:d} ".format(success, pending, total)
        else:
            message = "Build {:d}/{:d}".format(success, total)

        if total:
            view.set_status("github_build_status", message)

    def status_summary(self, success, failure, error, pending):
        text = ""
        if success:
            text += "{:d} success{}".format(success, "es" if success > 1 else "")
        if failure:
            if success and (error or pending):
                text += " , "
            elif success:
                text += " and "
            text += "{:d} failure{}".format(failure, "s" if failure > 1 else "")
        if error:
            if (success or failure) and pending:
                text += " , "
            elif success or failure:
                text += " and "
            text += "{:d} error{}".format(error, "s" if error > 1 else "")
        if pending:
            if success or failure or error:
                text += " and "
            text += "{:d} pending{}".format(pending, "s" if pending > 1 else "")

        return text

    def update_output_panel(self, contexts, success, failure, error, pending):
        window = self.view.window()

        preferece = sublime.load_settings("Preferences.sublime-settings")

        output_panel = window.get_output_panel("GitHubBuildStatus")
        output_panel.settings().set("color_scheme", preferece.get("color_scheme"))
        output_panel.settings().set("syntax", "github-build-status.sublime-syntax")
        output_panel.settings().set("github-build-status", True)

        def write(text):
            output_panel.run_command("append", {"characters": text})

        write(self.status_summary(success, failure, error, pending))

        if success + failure + error + pending:
            last_update_time = max([parse_time(status["updated_at"])
                                    for status in contexts.values()])
            write(" (" + dates.fuzzy(last_update_time, datetime.utcnow()) + ")\n\n")

            for i, (context, status) in enumerate(sorted(contexts.items())):
                write("{}: {} - {}\n".format(context, status["state"], status["description"]))


class GbsHandler(sublime_plugin.EventListener):

    def update_build_status(self, view):
        sublime.set_timeout_async(lambda: self.update_build_status_async(view))

    def update_build_status_async(self, view):
        if not view:
            return

        window = view.window()
        if not window:
            return

        window.run_command("gbs_fetch")
        view.run_command("gbs_render")

    def on_new(self, view):
        self.update_build_status(view)

    def on_load(self, view):
        self.update_build_status(view)

    def on_activated(self, view):
        self.update_build_status(view)

    def on_hover(self, view, point, hover_zone):
        if not view.settings().get("github-build-status", False):
            return

        window = view.window()
        if not window:
            return
        if window.id() not in builds:
            return
        if hover_zone != sublime.HOVER_TEXT:
            return
        if view.match_selector(point, "entity.name") == 0:
            return

        build = builds[window.id()]
        region = view.extract_scope(point)
        context = view.substr(region)

        url = build["contexts"][context]["target_url"]

        view.add_regions(
            context,
            [region],
            "meta",
            flags=sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)

        def on_navigate(action):
            if action == "open":
                webbrowser.open_new_tab(url)

        def on_hide():
            view.erase_regions(context)

        view.show_popup(
            URL_POPUP,
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            on_navigate=on_navigate, on_hide=on_hide)
