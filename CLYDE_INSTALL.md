# Clyde 安装说明

Clyde 是一只来自格拉斯哥的苏格兰高地牛桌宠，目前支持 Windows 和 Apple Silicon Mac。

## Windows 安装

适用 Windows 10/11 64 位系统。

1. 下载 `Clyde-Windows-v0.1.3.zip`。
2. 右键 ZIP，选择“全部解压缩”。
3. 打开解压后的文件夹。
4. 双击 `Clyde.exe`。

不需要安装 Python。请勿将 `Clyde.exe` 单独移出文件夹，它必须与 `_internal` 文件夹放在一起。

如果出现“Windows 已保护你的电脑”，点击“更多信息”后选择“仍要运行”。这是因为当前版本没有代码签名证书。

## macOS 安装

适用于 Apple Silicon Mac，包括 M1、M2、M3、M4 及后续芯片。

1. 下载 `Clyde-macOS-Apple-Silicon-v0.1.3.dmg`。
2. 双击打开 DMG。
3. 将 `Clyde.app` 拖入“应用程序”文件夹。
4. 从“应用程序”中启动 Clyde。

如果提示 Apple 无法验证 Clyde：

1. 点击“完成”，不要选择“移到废纸篓”。
2. 打开“系统设置 → 隐私与安全性”。
3. 找到被阻止的 Clyde，点击“仍要打开”。
4. 输入密码或使用 Touch ID 确认。

建议不要直接在 DMG 中长期运行 Clyde。

## 基本操作

- 左键按住 Clyde：拖动位置
- 右键 Clyde：打开功能菜单
- 将文件拖到 Clyde 身上：喂食文件
- `Awake — stand by`：清醒待命
- `Run about`：在桌面上随机活动
- `Rest — do not disturb`：安静睡觉
- `Back to bottom-right`：回到屏幕右下角
- `Quit Clyde`：完全退出

喂给 Clyde 的文件会进入系统回收站或废纸篓，并非永久删除，可以恢复。

## 退出与卸载

请先右键 Clyde，选择 `Quit Clyde`。

- Windows：删除解压后的整个 Clyde 文件夹。
- macOS：从“应用程序”中将 `Clyde.app` 移到废纸篓。

Clyde 不需要额外的卸载工具。

## 常见问题

### 双击后没有反应

检查 Clyde 是否已经出现在桌面角落。如果已经启动多个实例，请在任务管理器或“活动监视器”中结束旧进程后重试。

### Clyde 一直睡觉

右键 Clyde，选择 `Awake — stand by` 或 `Run about`。

### 文件被吃掉后去哪里了

文件会进入 Windows 回收站或 macOS 废纸篓，可以正常恢复。

### Intel Mac 可以使用吗

当前 macOS 安装包仅支持 Apple Silicon，即 M 系列芯片。Intel Mac 暂不支持。

### Windows 和 macOS 完全一样吗

角色形象、主要状态和喂食设定一致；受系统窗口和文件机制影响，部分动画及交互表现可能略有区别。
