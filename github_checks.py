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
from .utils.badge import DynamicBadge
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
<img width="20%" height="20%" src="res://Packages/GitHubChecks/images/link.png" />
</a>
</div>
</body>
"""


def parse_time(time_string):
    return datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%SZ")


class GitCommand:

    def github_checks_settings(self, key, default=None):
        s = sublime.load_settings("github_checks.sublime-settings")
        return s.get(key, default)

    def git(self, cmd, cwd=None):
        plat = sublime.platform()
        if not cwd:
            cwd = self.getcwd()
        if not cwd or not os.path.isdir(cwd):
            return

        if type(cmd) == str:
            cmd = [cmd]
        cmd = [self.github_checks_settings("git", "git")] + cmd
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


class GithubChecksFetchCommand(GitCommand, sublime_plugin.WindowCommand):
    timer = None
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

        if force and window.id() in builds:
            del builds[window.id()]

        if not branch:
            if verbose or self.github_checks_settings("debug", False):
                print("branch not found")
            return

        cooldown = self.github_checks_settings("cooldown", 60)
        if not force and time.time() - self.last_fetch_time < cooldown:
            return

        if time.time() - self.last_fetch_time < 1:
            # still, avoid too frequent refresh
            return

        self.folders = window.folders()
        self.last_fetch_time = time.time()
        self._branch = branch

        if force and self.timer:
            self.timer.cancel()
            self.timer = None

        if not self.timer:
            self.thread = threading.Thread(target=lambda: self.run_async(force, verbose))
            self.thread.start()

    def run_async(self, force=False, verbose=False):
        debug = self.github_checks_settings("debug", False)

        window = self.window
        if not window:
            return

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

        tracking_commit = self.query_branch_sha(remote_url, tracking_branch, verbose=verbose)
        if not tracking_commit:
            return

        checks = {}
        checks.update(self.query_workflows(
            remote_url, tracking_branch, tracking_commit, verbose=verbose))
        checks.update(self.query_status(
            remote_url, tracking_branch, tracking_commit, verbose=verbose))

        ignore_services = self.github_checks_settings("ignore_services", [])
        for service in ignore_services:
            if service in checks:
                del checks[service]

        builds[window.id()] = {
            "checks": checks
        }
        pending = sum(status["state"] == "pending" for status in checks.values())

        if checks and pending:
            self.timer = threading.Timer(
                int(self.github_checks_settings("refresh", 30)),
                lambda: sublime.set_timeout(
                    lambda: window.run_command("github_checks_fetch", {"force": True})))
            self.timer.start()

        view = window.active_view()
        if view:
            sublime.set_timeout(lambda: view.run_command("github_checks_render", {"force": force}))

        if verbose:
            window.status_message("GitHub Checks refreshed.")

    def query_branch_sha(self, remote_url, tracking_branch, verbose=False):
        debug = self.github_checks_settings("debug", False)

        token = self.github_checks_settings("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None

        path = "/repos/{owner}/{repo}/branches/{branch}".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            branch=tracking_branch
        )

        if debug:
            print("fetching from github branches api: {}/{}".format(
                    github_repo.owner, github_repo.repo))
        try:
            response = query_github(path, github_repo, token)
        except socket.gaierror:
            if verbose or debug:
                print("network error")
            return

        if response.status == 200 and response.is_json:
            return response.payload["commit"]["sha"]
        else:
            return

    def query_workflows(self, remote_url, tracking_branch, tracking_commit, verbose=False):
        debug = self.github_checks_settings("debug", False)

        token = self.github_checks_settings("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None
        headers = {"Accept": "application/vnd.github.v3+json"}

        path = "/repos/{owner}/{repo}/actions/runs?branch={branch}".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            branch=tracking_branch
        )

        if debug:
            print("fetching from github actions/runs api: {}/{}".format(
                    github_repo.owner, github_repo.repo))
        try:
            response = query_github(path, github_repo, token, headers=headers)
        except socket.gaierror:
            if verbose or debug:
                print("network error")
            return {}

        checks = {}
        if response.status == 200 and response.is_json:
            if response.payload["total_count"] > 0:
                workflow_runs = response.payload["workflow_runs"]
                for run in workflow_runs:
                    if run["head_commit"]["id"] != tracking_commit:
                        continue
                    if run["event"] != "push":
                        continue
                    name = run["name"]
                    run_id = run["id"]
                    workflow_checks = self.query_jobs(remote_url, name, run_id, verbose=verbose)
                    for check in workflow_checks:
                        workflow_checks[check]["created_at"] = run["created_at"]
                        workflow_checks[check]["updated_at"] = run["updated_at"]

                    checks.update(workflow_checks)

        else:
            if verbose or debug:
                print("request status: {:d}".format(response.status))
                if debug:
                    print(response.payload)
            return {}

        return checks

    def query_jobs(self, remote_url, run_name, run_id, verbose=False):
        debug = self.github_checks_settings("debug", False)

        token = self.github_checks_settings("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None
        headers = {"Accept": "application/vnd.github.v3+json"}

        path = "/repos/{owner}/{repo}/actions/runs/{run_id}/jobs".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            run_id=run_id
        )
        if debug:
            print("fetching from github actions/runs/jobs api: {}/{}".format(
                    github_repo.owner, github_repo.repo))
        try:
            response = query_github(path, github_repo, token, headers=headers)
        except socket.gaierror:
            if verbose or debug:
                print("network error")
            return {}

        checks = {}
        if response.status == 200 and response.is_json:
            if response.payload["total_count"] > 0:
                jobs = response.payload["jobs"]
                for job in jobs:
                    context = run_name + " / " + job["name"]
                    status = job["status"]
                    if status == "completed":
                        conclusion = job["conclusion"]
                        if conclusion == "success":
                            state = "success"
                        elif conclusion == "failure":
                            state = "failure"
                        elif conclusion == "neutral":
                            state = "neutral"
                        elif conclusion == "skipped":
                            state = "skipped"
                        else:
                            state = "error"
                    else:
                        state = "pending"

                    checks[context] = {
                        "state": state,
                        "context": context,
                        "description": state,
                        "target_url": job["html_url"]
                    }

        return checks

    def query_status(self, remote_url, tracking_branch, tracking_commit, verbose=False):
        debug = self.github_checks_settings("debug", False)

        token = self.github_checks_settings("token", {})
        github_repo = parse_remote_url(remote_url)
        token = token[github_repo.fqdn] if github_repo.fqdn in token else None

        path = "/repos/{owner}/{repo}/commits/{sha}/status".format(
            owner=github_repo.owner,
            repo=github_repo.repo,
            sha=tracking_commit
        )

        if debug:
            print("fetching from github status api: {}/{}".format(
                    github_repo.owner, github_repo.repo))
        try:
            response = query_github(path, github_repo, token)
        except socket.gaierror:
            if verbose or debug:
                print("network error")
            return {}

        checks = {}
        if response.status == 200 and response.is_json:
            for status in response.payload["statuses"]:
                context = status["context"]
                checks[context] = {
                    "state": status["state"],
                    "context": status["context"],
                    "description": status["description"],
                    "target_url": status["target_url"],
                    "created_at": status["created_at"],
                    "updated_at": status["updated_at"]
                }
        else:
            if verbose or debug:
                print("request status: {:d}".format(response.status))
                if debug:
                    print(response.payload)
            return {}

        return checks


badges = {}


class GithubChecksRenderCommand(sublime_plugin.TextCommand):

    last_render_time = 0
    build = None

    def run(self, _, force=False):
        if time.time() - self.last_render_time < 5:
            return
        self.last_render_time = time.time()
        sublime.set_timeout_async(lambda: self.run_async(force))

    def run_async(self, force):
        view = self.view
        window = view.window()
        if not window:
            return
        if window.id() not in builds:
            if view.id() in badges:
                badge = badges[view.id()]
                badge.erase()
                del badges[view.id()]
            return

        build = builds[window.id()]
        if not force and build == self.build:
            return

        if view.id() not in badges:
            badges[view.id()] = DynamicBadge(view, "badge#{:d}".format(view.id()))

        badge = badges[view.id()]

        self.build = build

        checks = build["checks"]
        success = sum(status["state"] == "success" for status in checks.values())
        failure = sum(status["state"] == "failure" for status in checks.values())
        error = sum(status["state"] == "error" for status in checks.values())
        skipped = sum(status["state"] == "skipped" for status in checks.values())
        pending = sum(status["state"] == "pending" for status in checks.values())

        sublime.set_timeout(
            lambda: self.update_output_panel(checks, success, failure, error, skipped, pending))

        if success + failure + error + pending:
            # ignore skipped
            message = "GitHub "
            if success:
                message = message + "{:d}✓".format(success)
            if failure + error:
                message = message + "{:d}✕".format(failure + error)
            if pending:
                message = message + "({:d}) {{indicator}}".format(pending)

            badge.set_status(message)

        else:
            badge.erase()
            badge = None

    def status_summary(self, success, failure, error, skipped, pending):
        text = ""
        if success:
            text += "{:d} successful".format(success)
        if failure:
            if success and (error or pending):
                text += " , "
            elif success:
                text += " and "
            text += "{:d} failed".format(failure)
        if error:
            if (success or failure) and pending:
                text += " , "
            elif success or failure:
                text += " and "
            text += "{:d} error".format(error)
        if skipped:
            if success or failure or error:
                text += " and "
            text += "{:d} skipped".format(skipped)
        if pending:
            if success or failure or error or skipped:
                text += " and "
            text += "{:d} pending".format(pending)

        total = success + failure + error + skipped + pending

        if total > 1:
            text += " checks"
        elif total > 0:
            text += " check"

        return text

    def update_output_panel(self, checks, success, failure, error, skipped, pending):
        window = self.view.window()
        if not window:
            return

        preferece = sublime.load_settings("Preferences.sublime-settings")

        output_panel = window.find_output_panel("GitHub Checks")
        if not output_panel:
            output_panel = window.create_output_panel("GitHub Checks")
            output_panel.settings().set("github-checks", True)
            output_panel.set_read_only(True)

        output_panel.settings().set("color_scheme", preferece.get("color_scheme"))
        output_panel.settings().set("syntax", "github-checks.sublime-syntax")
        sel = [s for s in output_panel.sel()]

        output_panel.set_read_only(False)
        output_panel.run_command("select_all")
        output_panel.run_command("left_delete")
        output_panel.set_read_only(True)

        def write(text):
            output_panel.set_read_only(False)
            output_panel.run_command("append", {"characters": text})
            output_panel.set_read_only(True)

        write(self.status_summary(success, failure, error, skipped, pending))

        if success + failure + error + pending:
            last_update_time = max([parse_time(status["updated_at"])
                                    for status in checks.values()])
            write(" (" + dates.fuzzy(last_update_time, datetime.utcnow()) + ") ")

            pt = output_panel.line(sublime.Region(0, 0)).end()

            output_panel.erase_phantoms("refresh")

            def on_navigate(action):
                window.run_command("github_checks_fetch", {"force": True, "verbose": True})

            output_panel.add_phantom(
                "refresh",
                sublime.Region(pt, pt),
                "<a href=\"open\">↺</a>",
                sublime.LAYOUT_INLINE,
                on_navigate=on_navigate
            )
            write("\n\n")

            for i, (_, status) in enumerate(sorted(checks.items())):
                if status["state"] == "success":
                    icon = "✓"
                elif status["state"] == "failure":
                    icon = "✕"
                elif status["state"] == "error":
                    icon = "⚠"
                elif status["state"] == "netural" or status["state"] == "skipped":
                    icon = "∅"
                else:
                    icon = "⧖"

                write("{} {} - {}\n".format(icon, status["context"], status["description"]))

        output_panel.sel().clear()
        output_panel.sel().add_all(sel)
        output_panel.show(output_panel.sel())


class GithubChecksHandler(sublime_plugin.EventListener):

    def update_build_status(self, view):
        sublime.set_timeout_async(lambda: self.update_build_status_async(view))

    def update_build_status_async(self, view):
        if not view:
            return

        window = view.window()
        if not window:
            return

        window.run_command("github_checks_fetch")
        view.run_command("github_checks_render")

    def on_new(self, view):
        self.update_build_status(view)

    def on_load(self, view):
        self.update_build_status(view)

    def on_activated(self, view):
        self.update_build_status(view)

    def on_hover(self, view, point, hover_zone):
        if not view.settings().get("github-checks", False):
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
        service = view.substr(region)

        url = build["checks"][service]["target_url"]

        view.add_regions(
            service,
            [region],
            "meta",
            flags=sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)

        def on_navigate(action):
            if action == "open":
                webbrowser.open_new_tab(url)

        def on_hide():
            view.erase_regions(service)

        view.show_popup(
            URL_POPUP,
            sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            on_navigate=on_navigate, on_hide=on_hide)


def plugin_unloaded():
    for badge in badges.values():
        badge.erase()
