# Dusk · Niri 桌面配置

包含 Niri、Waybar、控制中心、SwayNC、Rofi、Kitty、Neovim、Zsh + Zim、tmux、Fastfetch 和 Fcitx5 + Rime。浅色、深色和高透明主题可以在控制中心切换。天气、壁纸、媒体和系统状态都可在顶栏访问。

首次配置按第 1–3 节进行，第 3 节可按需选做。平时使用查看第 4–6 节，更新或回退查看第 7 节。Rofi 动画和 SwayNC 补丁的编译步骤在第 8 节。

## 1. 安装依赖

完整配置以 **Niri 26.04、Waybar 0.16、Rofi 2.1.1（Wayland）、SwayNC 0.12.6** 为验证基线。Niri 的背景模糊依赖 26.04 或更新版本。下列包名按发行版区分。桌面实机验证环境为 Arch Linux。

### Arch Linux

```sh
sudo pacman -Syu --needed git niri waybar rofi swaync swaybg swaylock kitty \
  python-gobject python-cairo gtk3 gtk-layer-shell playerctl wireplumber \
  brightnessctl wdisplays networkmanager nm-connection-editor bluez-utils \
  blueman pavucontrol adwaita-fonts noto-fonts-cjk ttf-nerd-fonts-symbols-mono \
  zsh tmux fastfetch neovim zstd
sudo pacman -S --needed fcitx5 fcitx5-gtk fcitx5-qt fcitx5-configtool \
  fcitx5-rime rime-luna-pinyin
```

`ttf-nerd-fonts-symbols-mono` 提供 **Symbols Nerd Font Mono**，并自动安装 `ttf-nerd-fonts-symbols-common`。上面的组件来自 Arch 正式仓库。使用其他中文社区软件时，可按社区说明另行添加签名校验的 Arch Linux CN 源。 [Arch Linux CN 仓库](https://github.com/archlinuxcn/repo)

### Debian

适用于 Debian 13（Trixie）及更新版本。Trixie 的仓库有常用依赖，Waybar 为 0.12，Rofi 1.7 系列早于本配置使用的原生 Wayland 版本。安装依赖后，按下面的「版本不足时」准备 Niri、Waybar 和 Rofi。 [Debian Waybar](https://packages.debian.org/trixie/waybar) · [Debian Rofi](https://packages.debian.org/trixie/rofi)

```sh
sudo apt update
sudo apt install git swaybg kitty python3-gi python3-gi-cairo \
  gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 playerctl wireplumber \
  brightnessctl network-manager network-manager-gnome bluez blueman \
  pavucontrol fonts-noto-cjk fontconfig zsh tmux neovim zstd
sudo apt install fcitx5 fcitx5-config-qt fcitx5-frontend-gtk3 \
  fcitx5-rime rime-data-luna-pinyin
```

用 `apt-cache policy sway-notification-center wdisplays fastfetch` 检查对应套件的候选版本。Trixie 提供 SwayNC 0.11，完整通知主题建议用上游 0.12.6 或更新版。 [Debian SwayNC 版本](https://packages.debian.org/search?keywords=sway-notification-center&searchon=sourcenames)

### Ubuntu

建议从 Ubuntu 26.04 LTS 开始。若尚未启用 Universe，先运行 `sudo add-apt-repository universe`。26.04 的 Waybar 0.15 和 Rofi 2.0 可用于尝试基础配置。要复现本仓库的效果，建议按下节准备验证基线版本，并单独安装 Niri。 [Ubuntu Waybar](https://packages.ubuntu.com/resolute/waybar) · [Ubuntu Rofi](https://packages.ubuntu.com/resolute/rofi)

```sh
sudo apt update
sudo apt install git waybar rofi sway-notification-center swaybg kitty \
  python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-gtklayershell-0.1 \
  playerctl wireplumber brightnessctl network-manager network-manager-gnome \
  bluez blueman pavucontrol fonts-noto-cjk fontconfig zsh tmux neovim zstd
sudo apt install fcitx5 fcitx5-config-qt fcitx5-frontend-gtk3 \
  fcitx5-rime rime-data-luna-pinyin
```

显示设置使用 `wdisplays`，终端启动摘要使用 `fastfetch`。用 `apt-cache policy wdisplays fastfetch` 检查候选包，或从各自上游安装。

### Fedora

优先使用 Fedora 45 或更新版。Fedora 44 提供 Niri 26.04，Waybar 为 0.15。若需要与本配置一致的顶栏行为，按下节准备较新的 Waybar。 [Fedora Niri](https://packages.fedoraproject.org/pkgs/niri/niri/) · [Fedora Waybar](https://packages.fedoraproject.org/pkgs/waybar/waybar/)

```sh
sudo dnf install git niri waybar rofi SwayNotificationCenter swaybg kitty \
  python3-gobject python3-cairo gtk3 gtk-layer-shell playerctl wireplumber \
  brightnessctl NetworkManager nm-connection-editor bluez blueman pavucontrol \
  google-noto-sans-cjk-fonts fontconfig zsh tmux fastfetch neovim zstd
sudo dnf install fcitx5 fcitx5-gtk fcitx5-rime
```

如缺少显示工具或简化拼音方案，可用 `dnf provides '*/wdisplays'` 和 `dnf provides '*/luna_pinyin_simp.schema.yaml'` 查询当前版本的软件包。

### 版本不足时

- **Niri**：从同发行版的软件源安装 26.04 或更新版。无合适包时，按上游说明安装 Rust 和系统开发依赖，构建稳定标签，并安装 `niri-session`、会话文件和 systemd 用户单元。只复制 `niri` 二进制会缺少图形会话集成。 [Niri 安装与构建](https://niri-wm.github.io/niri/Getting-Started.html)
- **Waybar**：构建或安装 0.16 或更新版，确保启用 Niri、MPRIS、GTK Layer Shell 和 StatusNotifier 托盘支持。 [Waybar 构建说明](https://github.com/Alexays/Waybar/wiki/Installation)
- **Rofi**：使用 2.1.1 或更新版的 Wayland 构建。运行 `rofi -help` 核实 Wayland 支持与 `-no-click-to-exit` 选项。 [Rofi 发行版](https://github.com/davatorium/rofi/releases)
- **SwayNC**：使用 0.12.6 或更新版可复现本仓库的通知主题和控制命令。 [SwayNC 安装说明](https://github.com/ErikReider/SwayNotificationCenter#installation)

### 字体

Waybar、Rofi 和控制中心的图标使用 **Symbols Nerd Font Mono**。Debian、Ubuntu 和 Fedora 如无同名字体包，从 Nerd Fonts 发布页下载 `NerdFontsSymbolsOnly.zip`，解压后安装符号字体。 [Nerd Fonts 发布页](https://github.com/ryanoasis/nerd-fonts/releases)

```sh
install -Dm644 SymbolsNerdFontMono-Regular.ttf \
  "$HOME/.local/share/fonts/SymbolsNerdFontMono-Regular.ttf"
fc-cache -f
fc-match "Symbols Nerd Font Mono"
```

界面优先使用 **Adwaita Sans**，Kitty 使用 **Adwaita Mono**，中文由 **Noto Sans CJK SC** 提供。发行版没有 Adwaita 字体时，可以从上游安装，或把 Kitty 的 `font_family` 改成已有的等宽字体。 [Adwaita 字体](https://gitlab.gnome.org/GNOME/adwaita-fonts)

## 2. 备份、安装配置并启动

### 备份和复制配置

以下命令使用默认配置目录 `~/.config`。从 Linux 克隆仓库并使用 `cp -a`，这样会保留主题符号链接和壁纸启动脚本的执行权限。

```sh
git clone https://github.com/scaraOvO/niri.git
cd niri
backup=$(mktemp -d "$HOME/.niri-backup-XXXXXX")
mkdir -p "$HOME/.config"
for name in niri waybar swaync rofi kitty fastfetch nvim tmux systemd fcitx5 hypr; do
  if [ -e "$HOME/.config/$name" ]; then
    cp -a "$HOME/.config/$name" "$backup/"
  fi
done
niri validate -c .config/niri/config.kdl &&
  cp -a .config/. "$HOME/.config/" &&
  printf '配置备份位于 %s\n' "$backup"
```

### 登录 Niri 并启用用户服务

从登录管理器选择 **Niri**，或在 TTY 手动运行 `niri-session`。在 **Niri 会话里的普通用户终端**启用用户服务。先退出 root shell，使用登录桌面的账号运行以下命令。

```sh
systemctl --user daemon-reload
systemctl --user enable --now dusk-appearance.timer dusk-weather.timer
systemctl --user enable --now swaync.service
```

若系统正在用 Mako 或 Dunst，先停止原通知服务。若发行版的 SwayNC 包未提供 `swaync.service`，可在 Niri 配置加 `spawn-at-startup "swaync"`，下次登录启动。NetworkManager、WirePlumber 和 BlueZ 由发行版管理，控制中心读取相应服务与硬件状态。亮度调节需要可用的背光设备。

## 3. 可选：中文输入与终端初始化

### Fcitx5 + Rime

Fcitx5 会随 Niri 启动。已随仓库提供 Fcitx5 配置和朙月拼音·简化字方案。若已有自己的 Rime 配置，保留原文件并在输入法设置中选用自己的方案。

```sh
rime="$HOME/.local/share/fcitx5/rime"
mkdir -p "$rime"
if [ ! -e "$rime/default.custom.yaml" ]; then
  install -m644 .local/share/fcitx5/rime/default.custom.yaml "$rime/"
fi
```

在图形会话的输入框里按 `Ctrl+Space` 切换中英文。Niri 下优先使用 Wayland 原生输入法接口。 [Fcitx Wayland 文档](https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland)

### Zsh + Zim

要使用 Zim，先备份自己已有的 `.zshrc` 和 `.zimrc`，再复制仓库文件。按 Zim 手动安装说明把 `zimfw.zsh` 放到 `~/.zim/` 后安装模块。 [Zim 手动安装](https://github.com/zimfw/zimfw#manual-installation)

```sh
backup=$(mktemp -d "$HOME/.dusk-shell-backup-XXXXXX")
for name in .zshrc .zimrc; do
  if [ -e "$HOME/$name" ]; then cp -a "$HOME/$name" "$backup/"; fi
done
cp -a .zshrc .zimrc "$HOME/"
ZIM_HOME="$HOME/.zim" zsh -c 'source "$ZIM_HOME/zimfw.zsh" install'
```

新 Kitty 窗口会创建独立的 tmux 会话，第一个窗格显示 Fastfetch。

## 4. 常用快捷键

| 入口 | 功能 |
| --- | --- |
| `Super+T` | 打开 Kitty |
| `Super+D` | 打开 Rofi，按 `Esc` 关闭 |
| `Super+N` | 打开通知中心 |
| `Super+Shift+N` | 切换勿扰 |
| `Super+Shift+O` | 显示或隐藏桌面小组件 |
| `Super+Ctrl+O` | 进入或退出桌面小组件编辑模式 |
| `Super+Z` | 展开或收起临时终端 |
| `Super+Ctrl+Space` | 跨工作区搜索窗口 |
| `Super+Ctrl+F8` | 打开显示器预设 |
| `Super+Alt+L` | 锁屏 |
| `Super+Shift+D` | 打开桌面快捷操作 |
| `Super+Ctrl+V` | 搜索剪贴板历史 |
| `Super+Ctrl+Shift+V` | 管理剪贴板历史 |
| Waybar 最右侧下拉箭头 | 打开控制中心，调整外观、媒体与设备、网络、蓝牙和壁纸 |
| Waybar 中间小岛 | 滚轮切换时间、日期、天气、Token 用量和系统占用，点击展开详情 |

## 5. 桌面功能

### 小岛

自动主题按本机时间在 **07:00** 切到浅色、**19:00** 切到深色。小岛读取本机 Codex、Claude Code 与 DeepSeek Harness 会话日志，没有可读记录时跳过 Token 页。小岛天气使用 Open-Meteo，展开后可查看五天预报、地图、日出日落和气象指标。地图使用 OpenStreetMap。最近查询的城市、已选壁纸和地图缓存保存在本机。 [Open-Meteo](https://open-meteo.com/) · [OpenStreetMap](https://www.openstreetmap.org/copyright)

小岛和桌面天气在本机共用缓存。运行 `dusk-weather.timer` 后，后台每 15 分钟刷新。

小岛使用 Niri 报告的屏幕共享和录制状态，点击小岛旁的红点可查看屏幕或窗口标题。

### 壁纸与配色

仓库自带 Arch 默认壁纸。通过 **控制中心 → 壁纸** 可以一键恢复系统默认，也能浏览图片目录下的 `wallpaper` 子目录。把图片放进去并点「重新扫描」后，点击缩略图即可切换。

在 **控制中心 → 外观**，可独立选择「壁纸取色」或「Dusk 原色」，并调节色彩强度。「随壁纸明暗」根据壁纸亮度选择浅色或深色，「定时」继续按 07:00／19:00 切换。「高透明」使用浅色主题的深色文字，并降低面板背景的不透明度。通过控制中心更换图片时配色即时更新。

壁纸生成的配色、本机图库和个人选择不随仓库分发。Niri 的 `wallpaper-palette.kdl` 由外观设置在本机生成。

### 场景、窗口归位与壁纸预览

按 `Super+Shift+D` 打开 Rofi 快捷操作，可搜索壁纸、通知中心、主题、场景与窗口归位设置。

控制中心「场景」提供日常、专注和演示。专注与演示会开启勿扰，并淡出桌面小组件。演示取消 Firefox 和 Code 的窗口透明效果。回到日常时恢复原状态。

同页可启用新窗口归位。Firefox 和 Kitty 打开在 `browse`，列宽分别约为 69% 和 30%；Code 打开在 `develop`，列宽约为 76%。已打开的窗口保留原位置。

点击壁纸缩略图会展开 Waybar、小岛和控制中心的配色预览，显示预估对比度。确认后才更换壁纸并启用壁纸取色。

### 终端、窗口与显示器

- `Super+Z` 展开或收起顶部 Kitty 终端，tmux 会话名为 `dusk-scratch`。点击桌面空白或切换到其他窗口也会自动收起。
- `Super+Ctrl+Space` 执行跨工作区窗口搜索。
- `Super+Ctrl+F8` 或控制中心的「显示器预设」可保存和套用布局。请先将显示器调整到目标状态，再保存为单屏、双屏或投影等预设。套用时 15 秒内未确认会自动回退。预设保存在 `~/.local/state/dusk-desktop/display-presets.json`，套用后的显示状态由 Niri 当前会话管理。

### 锁屏

Arch Linux 可用 `sudo pacman -S hyprlock python-gobject python-cairo` 安装锁屏依赖。按 `Super+Alt+L` 锁屏，输入 Linux 用户密码，再按回车解锁。
锁屏沿用当前桌面壁纸，通知仅显示条数。

可把自定义头像放在 `~/.config/hypr/avatar.png`。没有个人头像时显示用户名的前两个字符。
Hyprlock 不可用时会回退到 Swaylock。

## 6. 可选：剪贴板和小组件

### 剪贴板

剪贴板需要 `cliphist`、`wl-clipboard` 和 `flock`。Arch 可用 `sudo pacman -S --needed cliphist wl-clipboard`。Fedora 用 `dnf provides '*/cliphist'` 检查当前软件源。按 `Super+Ctrl+V` 搜索并恢复剪贴板，按 `Super+Ctrl+Shift+V` 删除单条、确认清空或暂停记录。

### 桌面小组件

桌面小组件随 Niri 启动，位于应用窗口后方。时钟、日期、天气、系统占用和 Docker 可独立摆放。组件使用局部背景模糊和纯白文字。天气沿用顶栏小岛保存的城市。

按 `Super+Ctrl+O` 进入编辑模式。Niri 会在当前输出切到空工作区，拖动桌面上的组件即可调整位置。工具条上的复选框可添加或移除组件。点击「完成」或按 `Esc` 返回原工作区。布局保存到 `$XDG_STATE_HOME/dusk-control/desktop-widgets.json`，默认位于 `~/.local/state/dusk-control/`。

#### Docker 小组件

Docker 小组件读取当前用户的 Docker CLI context，显示容器状态、CPU 和内存用量。安装 Docker CLI 并确认 `docker ps` 能访问 daemon 后即可使用。组件可在编辑工具条中单独开关。

Arch Linux 使用 Rootless Docker 时，可在已经启用 Arch Linux CN 源的环境中安装并启用用户 socket。 [Docker Rootless 文档](https://docs.docker.com/engine/security/rootless/)

```sh
sudo pacman -S --needed docker docker-rootless-extras rootlesskit slirp4netns
systemctl --user enable --now docker.socket
docker context inspect rootless >/dev/null 2>&1 || \
  docker context create rootless --docker "host=unix://$XDG_RUNTIME_DIR/docker.sock"
docker context use rootless
docker ps
```

Debian、Ubuntu 和 Fedora 可沿用已配置的 Docker context，或按 Docker 官方说明配置 Rootless Docker。

## 7. 更新与回退

在 Arch 或 Fedora 的普通用户终端，从仓库根目录运行：

```sh
tools/dusk-config check
tools/dusk-config plan
tools/dusk-config apply
```

`check` 报告依赖、用户服务和可选编译版的状态。`plan` 只显示差异；`apply` 先验证 Niri 配置，再备份并更新仓库管理的 `.config` 文件。`rollback` 使用输出的备份路径，遇到更新后另行修改的文件会停止。备份文件可以用来手工合并。已生成的配色和本机主题选择会保留。

需要撤销上次更新时，把下面的路径替换为 `apply` 打印的备份路径。

```sh
tools/dusk-config rollback /path/to/printed/backup
```

## 8. 可选编译

### Rofi 弹入动画和分离式磨砂

系统自带的 Rofi 可直接使用。启用弹入动画，以及只对搜索框和结果列表做模糊，需要编译本节的 Wayland 版本。补丁和协议定义都在仓库中。 [Rofi 源码补丁](.config/rofi/wayland-opening.patch) · [Wayland 背景效果协议](.config/rofi/ext-background-effect-v1.xml)

按发行版安装构建依赖。

**Arch Linux**

```sh
sudo pacman -S --needed gcc meson ninja pkgconf flex bison curl git \
  glib2-devel cairo pango gdk-pixbuf2 libxkbcommon xkeyboard-config \
  wayland wayland-protocols
```

**Debian / Ubuntu**

```sh
sudo apt install build-essential meson ninja-build pkg-config flex bison curl git \
  libglib2.0-dev libcairo2-dev libpango1.0-dev libgdk-pixbuf-2.0-dev \
  libxkbcommon-dev xkb-data libwayland-dev libwayland-bin wayland-protocols
```

**Fedora**

```sh
sudo dnf install gcc meson ninja-build pkgconf-pkg-config flex bison curl git \
  glib2-devel cairo-devel pango-devel gdk-pixbuf2-devel libxkbcommon-devel \
  xkeyboard-config wayland-devel wayland-protocols-devel
```

在本仓库根目录，用普通用户运行下面的命令。构建使用带有子项目源码的官方发行压缩包。 [Rofi 2.1.1 发行页](https://github.com/davatorium/rofi/releases/tag/2.1.1)

```sh
(
  set -eu
  repo=$(pwd -P)
  build_dir=$(mktemp -d)
  cd "$build_dir"
  curl -fL https://github.com/davatorium/rofi/releases/download/2.1.1/rofi-2.1.1.tar.gz \
    -o rofi-2.1.1.tar.gz
  printf '%s\n' '5fe33afce841994eebfc0302ba869e7b9c035b97c26858fb0142a54a1627d3e4  rofi-2.1.1.tar.gz' | sha256sum -c -
  tar -xzf rofi-2.1.1.tar.gz
  cd rofi-2.1.1
  cp "$repo/.config/rofi/ext-background-effect-v1.xml" protocols/
  git apply "$repo/.config/rofi/wayland-opening.patch"
  meson setup build -Dxcb=disabled -Dwayland=enabled -Dcheck=disabled
  meson compile -C build
  meson test -C build --no-rebuild
  install -Dm755 build/rofi "$HOME/.local/libexec/dusk-rofi/rofi"
)
```

按第 2 节复制配置后，`Super+D` 会优先运行用户目录里的构建，并保留系统 Rofi 作为备用。模糊范围由 Niri 的 Wayland 背景效果协议控制。弹入动画、两块独立的模糊区域和编译流程已在 Arch Linux 验证。

### SwayNC 弹窗文字居中补丁

原版 SwayNC 可使用本仓库的通知样式。小岛正下方的弹窗采用 248 px 宽的圆角底板。背景模糊通过 GTK 的 `backdrop-filter` 和 Niri 的 Wayland 背景效果协议实现，已在 GTK 4.24.2 上验证。

弹窗的标题和正文在横向、竖向同时居中，需要应用本仓库的补丁，通知中心列表沿用原版布局。 [SwayNC 源码补丁](.config/swaync/popup-center.patch)

Arch Linux 的构建依赖如下。

```sh
sudo pacman -S --needed gcc meson ninja pkgconf vala sassc blueprint-compiler \
  gtk4 gtk4-layer-shell libadwaita granite7 libgee json-glib libpulse \
  glib2-devel wayland curl git
```

Debian、Ubuntu 或 Fedora 使用同一套构建命令。先安装对应的开发包，使 `pkg-config --modversion gtk4 gtk4-wayland gtk4-layer-shell-0 libadwaita-1 granite-7 gee-0.8 json-glib-1.0 wayland-client libpulse` 能返回版本，并准备 `valac`、`sassc`、`blueprint-compiler`、Meson、Ninja 和 C 编译器。发行版自带组件过旧时可继续使用原版通知服务。

从仓库根目录运行以下命令，将构建安装到当前用户的目录。 [SwayNC 0.12.6 发行页](https://github.com/ErikReider/SwayNotificationCenter/releases/tag/v0.12.6)

```sh
(
  set -eu
  repo=$(pwd -P)
  build_dir=$(mktemp -d)
  cd "$build_dir"
  curl -fL https://codeload.github.com/ErikReider/SwayNotificationCenter/tar.gz/refs/tags/v0.12.6 \
    -o swaync-0.12.6.tar.gz
  printf '%s\n' '0c844eb5c9524f924495bd4145e5db575096de36f3ec87fb37e4c1ed6eacb897  swaync-0.12.6.tar.gz' | sha256sum -c -
  tar -xzf swaync-0.12.6.tar.gz
  cd SwayNotificationCenter-0.12.6
  git apply "$repo/.config/swaync/popup-center.patch"
  meson setup build --sysconfdir=/etc -Dman-pages=false
  meson compile -C build
  install -Dm755 build/src/swaync "$HOME/.local/libexec/dusk-swaync/swaync"
)
```

按第 2 节复制配置后，在 Niri 的普通用户终端运行以下命令。随仓库提供的 systemd 覆盖配置会优先使用本机构建，并以发行版的 SwayNC 作为备用。

```sh
systemctl --user daemon-reload
systemctl --user restart swaync.service
notify-send '通知预览' '标题和正文均居中'
```

若通过 Niri 直接启动 SwayNC，可使用 `spawn-at-startup "sh" "-c" "exec \"$HOME/.config/swaync/launch\""` 调用同一个启动脚本。
