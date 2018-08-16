import sublime
import sublime_plugin
import subprocess
import threading
from datetime import datetime
from .utils import dates
import time
import os
import socket
from .query.github import query_github, parse_remote_url


def plugin_loaded():
    pass


def plugin_unloaded():
    pass


def parse_time(time_string):
    return datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")


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

    def run(self, force=False, verbose=False):
        window = self.window
        if self.folders and self.folders != window.folders():
            force = True

        if not force and time.time() - self.last_fetch_time < 1:
            return

        self.folders = window.folders()
        self.last_fetch_time = time.time()

        if force and self.thread:
            self.thread.cancel()
            self.thread = None

        if not self.thread:
            sublime.set_timeout_async(lambda: self.run_async(force, verbose))

    def run_async(self, force=False, verbose=False):

        window = self.window
        if not window:
            return

        s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
        refresh = s.get("refresh", 30)
        debug = s.get("debug", False)

        gm = GitManager(window)
        branch = gm.branch()
        if not branch:
            if verbose or debug:
                print("branch not found")
            return
        remote = gm.run_git(["config", "branch.{}.remote".format(branch)])
        if not remote:
            if verbose or debug:
                print("remote not found")
            return
        remote_url = gm.run_git(["config", "remote.{}.url".format(remote)])
        if not remote_url:
            return
        tracking_branch = gm.run_git(["config", "branch.{}.merge".format(branch)])
        if not tracking_branch or not tracking_branch.startswith("refs/heads/"):
            return
        tracking_branch = tracking_branch.replace("refs/heads/", "")

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
                if context not in contexts or status["state"] != "pending":
                    contexts[context] = {
                        "state": status["state"],
                        "description": status["description"],
                        "target_url": status["target_url"],
                        "created_at": parse_time(status["created_at"]),
                        "updated_at": parse_time(status["updated_at"])
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

        view = window.active_view()
        if view:
            view.run_command("gbs_update")

        if verbose:
            window.status_message("GitHub build status refreshed.")


class GbsUpdateCommand(sublime_plugin.TextCommand):

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
        success = len([status for status in contexts.values() if status["state"] == "success"])
        failure = len([status for status in contexts.values() if status["state"] == "failure"])
        error = len([status for status in contexts.values() if status["state"] == "error"])
        pending = len([status for status in contexts.values() if status["state"] == "pending"])
        total = success + failure + error + pending

        self.update_output_panel(contexts, success, failure, error, pending)

        if pending:
            message = "Build {:d}({:d})/{:d} ".format(success, pending, total)
        else:
            message = "Build {:d}/{:d}".format(success, total)

        if total:
            view.set_status("github_build_status", message)

    def update_output_panel(self, contexts, success, failure, error, pending):
        window = self.view.window()

        output_panel = window.get_output_panel("GitHubBuildStatus")

        def write(text):
            output_panel.run_command("append", {"characters": text})

        if success:
            write("{:d} success{}".format(success, "es" if success > 1 else ""))
        if failure:
            if success and (error or pending):
                write(" , ")
            elif success:
                write(" and ")
            write("{:d} failure{} ".format(failure, "s" if failure > 1 else ""))
        if error:
            if (success or failure) and pending:
                write(" , ")
            elif success or failure:
                write(" and ")
            write("{:d} error{} ".format(error, "s" if error > 1 else ""))
        if pending:
            if success or failure or error:
                write(" and ")
            write("{:d} pending{} ".format(pending, "s" if pending > 1 else ""))

        if success + failure + error + pending:
            last_update_time = max([status["updated_at"] for status in contexts.values()])
            write(" (" + dates.fuzzy(last_update_time) + ")\n\n")

            for context, status in sorted(contexts.items()):
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
        view.run_command("gbs_update")

    def on_new(self, view):
        self.update_build_status(view)

    def on_load(self, view):
        self.update_build_status(view)

    def on_activated(self, view):
        self.update_build_status(view)
