# 致谢与素材来源 / Credits & Asset Sources

本项目的代码与素材来自三个开源项目，各自遵循不同的许可协议。**代码**采用 GPL-3.0，**素材**分别遵循其原始许可。

This project builds on three open-source projects. **Code** is licensed under GPL-3.0; **assets** keep their original licenses.

---

## 1. 设备端框架 / Device-side framework

**MadLongTom/holopet** — https://github.com/MadLongTom/holopet

提供 HoloCubic 设备端的 Lua 应用框架（LVGL 渲染、WebUI、配置页、字体模块）。

- 许可 **MIT License**
- 本项目的 `app/` 目录基于其 `package/` 改造而来：改名为 HoloPet、接入 DSH 事件源、重做两个界面、增加皮肤与动作系统、音效、配色、显示项开关等。

```
MIT License

Copyright (c) MadLongTom

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

## 2. 动作素材 / Animation assets

**PC2005-cloud/dsh-pet** — https://github.com/PC2005-cloud/dsh-pet

`app/assets/skins/pc2005/` 下的全部动作（114 个动作，三档速度 + 88×88 缩略图）以及 `docs/img/action-map.png` 中的动作说明，均来自该项目。

- 许可 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享 4.0 国际）
- https://creativecommons.org/licenses/by-nc-sa/4.0/
- 原形象设计版权归原作者；本项目仅做格式转换（WebM → 索引 GIF、缩放、调色板量化），未修改画面内容
- **非商业使用**：请勿将本项目素材用于商业用途

动画体系的设计（idle / turn / drag / clicks / moves / categories / events / sleep 的分类方式、`leadSec`/`tailSec` 衔接参数、workStatus 六档状态映射）同样来自该项目的 `config.jsonc`。

---

## 3. 鲸鱼娘皮肤 / Whale-girl skin

**zhu1090093659/dsh-pet** — https://github.com/zhu1090093659/dsh-pet

`app/assets/skins/whale/` 下的动作素材。

- 许可 **BSD-3-Clause**
- 本项目将其从 192×208 精灵表切帧、转换为 160×160 索引 GIF

```
BSD 3-Clause License

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software
   without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED.
```

---

## 4. 本项目原创部分 / Original work

以下内容为本项目原创，遵循 GPL-3.0：

- `plugin/dsh-pet-holocubic/` — DSH 插件（把 agent 状态通过 HTTP/SSE 暴露到局域网）
- `app/skin.lua`、`app/sound.lua`、`app/dsh_client.lua` — 皮肤系统、音效播放、DSH 协议适配
- `app/main.lua`、`app/web.lua` 中的改造部分 — 双界面布局、动作变体系统、走动状态机、配色与显示项、事件音效映射、B 页上下文面板
- `tools/` 下的全部转换与部署脚本
- `docs/` 下的架构图、示意图、使用说明

---

## 5. 未使用但调研过的项目 / Researched but not used

- **mjw-git/dsh-pet** — 其默认精灵图（像素白龙）在源码中仅注明 "the user-provided dragon sprite"，**没有明确的许可声明**，因此本项目**未包含**该素材。同学如需使用请自行确认授权。
