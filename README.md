# GitHub Checks

![aug-29-2018 07-15-11](https://user-images.githubusercontent.com/1690993/44784347-54ed1f80-ab5b-11e8-93c2-11c37b70856f.gif)


Display GitHub checks in Sublime Text. 

The badge: `Checks #✓#x(#)` where `x` is the number of successful builds, `y` is the number of failures + errors (if any) and `z` is the number of pendings.


## Installation

GitHubChecks is available to be installed via Package Control.


To install manually, clone the package manually to your Package directory. It would be eventually published to Package Control once it gets more mature.

```sh
# on macOS
cd "$HOME/Library/Application Support/Sublime Text 3/Packages"
# on Linux
cd $HOME/.config/sublime-text-3/Packages
# on Windows (PowerShell)
cd "$env:appdata\Sublime Text 3\Packages\"

git clone git@github.com/randy3k/GitHubChecks.git
```

## Show Checks Details

Run `GitHub Checks: Details`

<img width="800" src="https://user-images.githubusercontent.com/1690993/44185676-eaf86300-a0e2-11e8-9273-348313729e87.png">


## Settings

You are also recommended to provide your own [github api token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) to allow more frequent refreshes and access to your private repos. Simply run `Preference: GitHub Checks` and edit the `token` setting.