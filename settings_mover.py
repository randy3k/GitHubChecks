import sublime

import os


def update_settings():
    default_settings = {
            "git": "git",
            "token": {},
            "refresh": 30,
            "cooldown": 60,
            "ignore_services": ["github/pages"],
            "debug": False
    }

    s = sublime.load_settings("GitHubBuildStatus.sublime-settings")
    t = sublime.load_settings("github_checks.sublime-settings")

    for k in default_settings.keys():
        svalue = s.get(k)
        tvalue = t.get(k)
        if svalue and svalue != default_settings[k] and tvalue == default_settings[k]:
            t.set(k, svalue)
            sublime.save_settings("github_checks.sublime-settings")

    f = os.path.join(sublime.packages_path(), "User", "GitHubBuildStatus.sublime-settings")
    if os.path.exists(f):
        os.remove(f)


def plugin_loaded():
    f = os.path.join(sublime.packages_path(), "User", "GitHubBuildStatus.sublime-settings")
    g = os.path.join(sublime.packages_path(), "User", "github_checks.sublime-settings")
    if os.path.exists(f) and not os.path.exists(g):
        update_settings()
