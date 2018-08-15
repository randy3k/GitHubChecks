# GitHub Build Status

<img width="255" alt="screen shot 2018-08-15 at 1 23 02 am" src="https://user-images.githubusercontent.com/1690993/44132816-f0c5145e-a029-11e8-9738-07d05491f57d.png">

Display GitHub CI build status in Sublime Text. 

The badge: `Build x(y)/z` where `x` is the number of successful builds, `y` is the number of pendings (if any) and `z` is the total.


## Installation

To install, clone the package manually to your Package directory. It would be eventually published to Package Control once it gets more mature.

```sh
# on macOS
cd "$HOME/Library/Application Support/Sublime Text 3/Packages"
# on Linux
cd $HOME/.config/sublime-text-3/Packages
# on Windows (PowerShell)
cd "$env:appdata\Sublime Text 3\Packages\"

git clone git@github.com:randy3k/GitHubBuildStatus.git
```

## Settings

You are also recommended to provide your own [github api token](https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/) to allow more frequent refresh and access to your private repo. Simply run `Preference: GitHub Build Status` and edit the `token` setting.