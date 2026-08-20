# Clyde 🐂

一只来自格拉斯哥的苏格兰高地牛桌宠。

Clyde 戴着格拉斯哥标志性的交通锥，在桌面上四处奔跑。累了会坐下来喘气，或者窝着安静睡觉。你也可以把不需要的文件喂给它——文件会进入系统回收站，需要时仍能恢复。

> “I’m Clyde, from Glasgow. Do you like Scotland?”

![Clyde](clyde-assets/sprites/clyde-sit.png)

## 它会做什么

- 在桌面范围内随机奔跑并自动转身
- 跑累后停下来休息和喘气
- 安静地窝着睡觉，并显示 `Zzz`
- 支持鼠标拖动位置
- 接收拖到身上的一个或多个文件
- 咀嚼文件并将其移入系统回收站或废纸篓
- 支持清醒、活动和休息三种状态

## 三种状态

### Awake — stand by

Clyde 保持清醒并原地待命，不会擅自在桌面上乱跑。

### Run about

Clyde 会在屏幕范围内随机奔跑。累了会停下来喘气，但不会真正睡着。

### Rest — do not disturb

Clyde 会窝下来睡觉，不再到处乱跑，适合工作时开启。

## 喂食文件

把一个或多个文件拖到 Clyde 身上，它会先询问：

> “This one?”  
> “All of these?”

选择 `Aye` 后，Clyde 会处理并咀嚼文件。吃完后，它可能会告诉你：

> “Still not as good as Scottish whisky.”

如果选择 `Not that one` 或 `No, leave them`，文件会被完整保留。

> 喂食相当于将文件移入系统回收站或废纸篓，并非永久删除。误喂的文件仍可恢复。

## 右键菜单

- `Awake — stand by`：清醒待命
- `Run about`：在桌面上活动
- `Rest — do not disturb`：安静睡觉
- `Feed Clyde files…`：从文件选择器喂食
- `Open Recycle Bin / Trash`：打开回收站或废纸篓
- `Back to bottom-right`：回到屏幕右下角
- `About Clyde`：查看 Clyde 的介绍
- `Quit Clyde`：完全退出

## 下载与安装

请前往 [Releases](https://github.com/watermud-hr/leftover-pet/releases) 下载 Clyde v0.1.3：

- Windows 10/11 x64：`Clyde-Windows-v0.1.3.zip`
- Apple Silicon Mac（M1/M2/M3/M4）：`Clyde-macOS-Apple-Silicon-v0.1.3.dmg`
- 两个平台的详细步骤：`Clyde-Windows与macOS安装说明.md`

Windows 用户完整解压后双击 `Clyde.exe`；macOS 用户打开 DMG 后，将 `Clyde.app` 拖入“应用程序”。

当前构建没有商业代码签名。Windows SmartScreen 可能需要选择“更多信息 → 仍要运行”；macOS 首次启动可能需要在“系统设置 → 隐私与安全性”中选择“仍要打开”。

## 为什么叫 Clyde？

Clyde 的名字来自克莱德河（River Clyde）——那条贯穿格拉斯哥，也见证了这座城市工业、港口和生活变迁的河流。

它头顶的交通锥，则来自格拉斯哥最有名的城市趣闻：市民经常给皇家交易广场上的惠灵顿公爵雕像戴上交通锥。久而久之，它也成了格拉斯哥幽默、叛逆和城市性格的一部分。

## 源码运行

需要 Python 3.11+：

```bash
python -m pip install PySide6 send2trash
python clyde_pet_macos.py
```

## 当前版本

`v0.1.3`

Windows 与 macOS 使用相同的角色形象和核心设定；受两个系统的窗口与文件机制影响，部分动画及交互表现可能略有不同。
