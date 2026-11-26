# Niri 桌面配置

Arch Linux 上的 Dusk 桌面配置，包含 Niri、Waybar、Kitty、Rofi、Neovim、tmux、Fastfetch 和 Zsh + Zim。

## 使用

- 先备份现有配置，再把仓库 `.config/` 中所需的应用目录复制到 `~/.config/`。
- 如需使用 Zsh 配置，将 `.zshrc` 和 `.zimrc` 复制到主目录。安装 [Zim](https://github.com/zimfw/zimfw) 后运行 `zimfw install` 安装模块。
- Niri 会启动 `waybar` 和 `swaybg`。`Mod+D` 打开 Rofi，`Mod+T` 打开 Kitty，新 Kitty 终端会启动 tmux。
