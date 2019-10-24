import sublime

import os


def update_settings():
    keys = [
            "git",
            "token",
            "refresh",
            "cooldown",
            "ignore_services",
            "debug"
           ]

    s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
    t = sublime.load_settings("github_checks.sublime-settings")

    for k in keys:
        svalue = s.get(k)
        tvalue = t.get(k)
        if svalue and tvalue is None:
            t.set(k, svalue)
            sublime.save_settings("github_checks.sublime-settings")

    f = os.path.join(sublime.packages_path(), "User", "GitHubBuildStatus.sublime-settings")
    if os.path.exists(f):
        os.remove(f)


def plugin_loaded():
    f = os.path.join(sublime.packages_path(), "User", "GitHubBuildStatus.sublime-settings")
    if os.path.exists(f):
        update_settings()
