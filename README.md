# Niri 桌面配置

Arch Linux 上的 Dusk 桌面配置，包含 Niri、Waybar、Kitty、Rofi、Neovim、tmux、Fastfetch 和 Zsh + Zim。

## 使用

1. 安装所需的应用，先备份现有配置，再把仓库 `.config/` 中所需的应用目录复制到 `~/.config/`。Niri 使用 `swaybg` 设置咖啡壁纸，Kitty 使用 Adwaita Mono，Waybar 与 Rofi 使用 Adwaita Sans。
2. 将 `.zshrc` 和 `.zimrc` 复制到主目录。按 [Zim 的手动安装说明](https://github.com/zimfw/zimfw#manual-installation) 将 `zimfw.zsh` 放到 `~/.zim/`，然后运行 `ZIM_HOME="$HOME/.zim" zsh -c 'source "$ZIM_HOME/zimfw.zsh" install'`。
3. 在 Niri 中，`Mod+D` 打开 Rofi，`Mod+T` 打开 Kitty。新的 Kitty 终端会启动独立的 tmux 会话，并在第一个窗格显示 Fastfetch。
