import sublime
import sublime_plugin
import subprocess
import threading
import time
import os
import socket
from .query.github import query_github, parse_remote_url


def plugin_loaded():
    pass


def plugin_unloaded():
    pass


class GitManager:
    def __init__(self, window):
        self.window = window
        self.view = window.active_view()
        s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
        self.git = s.get("git", "git")

    def run_git(self, cmd, cwd=None):
        plat = sublime.platform()
        if not cwd:
            cwd = self.getcwd()
        if not cwd or not os.path.isdir(cwd):
            return

        if type(cmd) == str:
            cmd = [cmd]
        cmd = [self.git] + cmd
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
        f = self.view.file_name() if self.view else None
        cwd = None
        if f:
            cwd = os.path.dirname(f)
        if not cwd:
            window = self.view.window()
            if window and window.folders():
                cwd = window.folders()[0]
        return cwd

    def branch(self):
        return self.run_git(["symbolic-ref", "HEAD", "--short"])

    def remote_url(self):
        branch = self.branch()
        if not branch:
            return

        remote = self.run_git(["config", "branch.{}.remote".format(branch)])
        if not remote:
            return

        remote_url = self.run_git(["config", "remote.{}.url".format(remote)])
        if not remote_url:
            return

        return remote_url


builds = {}


class GbsFetchCommand(sublime_plugin.WindowCommand):
    thread = None
    last_fetch_time = 0
    folders = None

    def run(self, force=False):
        window = self.window
        if self.folders and self.folders != window.folders():
            force = True

        if not force and time.time() - self.last_fetch_time < 1:
            return

        self.last_fetch_time = time.time()

        if force and self.thread:
            self.thread.cancel()
            self.thread = None

        if not self.thread:
            sublime.set_timeout_async(lambda: self.run_async())

    def run_async(self):

        window = self.window
        if not window:
            return

        s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
        refresh = s.get("refresh", 30)

        gm = GitManager(window)
        branch = gm.branch()
        if not branch:
            return
        remote = gm.run_git(["config", "branch.{}.remote".format(branch)])
        if not remote:
            return
        remote_url = gm.run_git(["config", "remote.{}.url".format(remote)])
        if not remote_url:
            return
        head_sha = gm.run_git(["rev-parse", "HEAD"])
        if not head_sha:
            return
        head_sha = head_sha

        self.thread = threading.Timer(
            int(refresh),
            lambda: window.run_command("gbs_fetch", {"force": True}))
        self.thread.start()

        token = s.get("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None

        path = "/repos/{owner}/{repo}/statuses/{branch}".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            branch=branch
        )

        try:
            reponse = query_github(path, github_repo, token)
        except socket.gaierror:
            return

        contexts = {}
        if reponse.status == 200:
            if reponse.is_json:
                for status in reponse.payload:
                    context = status["context"]
                    if context not in contexts or status["state"] != "pending":
                        contexts[context] = {
                            "state": status["state"],
                            "description": status["description"]
                        }

        if "github/pages" in contexts:
            del contexts["github/pages"]

        builds[window.id()] = {
            "contexts": contexts
        }

        view = window.active_view()
        if view:
            view.run_command("gbs_update")


class GbsUpdateCommand(sublime_plugin.TextCommand):

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
        contexts = build["contexts"]
        success = 0
        failure = 0
        error = 0
        pending = 0
        for status in contexts.values():
            success += status["state"] == "success"
            failure += status["state"] == "failure"
            error += status["state"] == "error"
            pending += status["state"] == "pending"
        total = success + failure + error + pending

        if pending:
            message = "Build {:d}/{:d} ({:d})".format(success, total, pending)
        else:
            message = "Build {:d}/{:d}".format(success, total)

        if total:
            view.set_status("github_build_status", message)


class GitHubBuildStatusHandler(sublime_plugin.EventListener):

    def update_build_status(self, view):
        sublime.set_timeout_async(lambda: self.update_build_status_async(view))

    def update_build_status_async(self, view):
        if not view:
            return

        window = view.window()
        if not window:
            return

        window.run_command("gbs_fetch")
        view.run_command("gbs_update")

    def on_new(self, view):
        self.update_build_status(view)

    def on_load(self, view):
        self.update_build_status(view)

    def on_activated(self, view):
        self.update_build_status(view)
