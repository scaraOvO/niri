# Niri 桌面配置

Arch Linux 上的 Dusk 桌面配置，包含 Niri、Waybar、SwayNotificationCenter、Kitty、Rofi、Neovim、tmux、Fastfetch 和 Zsh + Zim。

## 使用

1. 安装所需应用，备份现有配置后，把仓库 `.config/` 下所需的应用目录复制到 `~/.config/`。Niri 使用 `swaybg` 加载咖啡壁纸。
2. 将 `.zshrc` 和 `.zimrc` 复制到主目录。按 [Zim 的手动安装说明](https://github.com/zimfw/zimfw#manual-installation) 将 `zimfw.zsh` 放到 `~/.zim/`，再运行 `ZIM_HOME="$HOME/.zim" zsh -c 'source "$ZIM_HOME/zimfw.zsh" install'`。
3. 安装 `swaync` 后，在 Niri 会话的终端运行 `systemctl --user enable --now swaync.service`。如果另一套通知服务正在运行，先停止它。
4. `Mod+D` 打开 Rofi，`Mod+T` 打开 Kitty，`Mod+N` 切换通知中心，`Mod+Shift+N` 切换勿扰。新的 Kitty 终端会启动独立的 tmux 会话，并在第一个窗格显示 Fastfetch。

## Waybar 字体

在 Arch Linux 上安装 `sudo pacman -S --needed ttf-nerd-fonts-symbols-mono`，然后重启 Waybar。

- `ttf-nerd-fonts-symbols-mono` 提供 **Symbols Nerd Font Mono**，用于工作区、时钟、CPU、内存、网络、音量和通知图标。
- `ttf-nerd-fonts-symbols-common` 随上面的包一同安装，提供共享 Fontconfig 配置。
- 正文仍使用桌面已有的 **Adwaita Sans**。
