#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把马善政毛笔楷书子集化成网页可用的 WOFF2。

原理: 5.6MB 的完整字库含 7015 字形, 但页面只用到一百多个字。
      按实际用到的字符裁剪 → 体积降到几十 KB。

用法: py subset_font.py
      首次运行会自动下载原始 TTF(Google Fonts 官方源, SIL OFL 可商用)
输出: mashanzheng-sub.woff2
"""
import io
import json
import os
import re
import urllib.request
from fontTools import subset

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, 'mashanzheng.ttf')
OUT = os.path.join(HERE, 'mashanzheng-sub.woff2')
# Google Fonts 官方直链(字体本身是 SIL OFL 1.1, 免费商用)
SRC_URL = 'https://fonts.gstatic.com/s/mashanzheng/v18/NaPecZTRCLxvwo41b4gvzkXaRMQ.ttf'

if not os.path.exists(SRC):
    print('原始 TTF 不存在, 从 Google Fonts 下载…')
    urllib.request.urlretrieve(SRC_URL, SRC)
    print('已下载: %.1f MB' % (os.path.getsize(SRC) / 1024 / 1024))
    print('(子集化完成后可删除该文件, 需要时重跑本脚本会自动重下)')
    print()

# ── 1. 收集页面实际会显示的所有字符 ──
chars = set()

# 1a. 所有地名(从 photos.json 和 index.html 的 CITIES 一并取)
pj = os.path.join(ROOT, 'photos.json')
if os.path.exists(pj):
    with io.open(pj, encoding='utf-8') as f:
        chars |= set(json.load(f).keys())

html = io.open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
# CITIES 里的 name 字段
for m in re.finditer(r"name:\s*'([^']+)'", html):
    chars |= set(m.group(1))
# 省份名
for m in re.finditer(r"prov:\s*'([^']+)'", html):
    chars |= set(m.group(1))

# 1b. 界面上会出现的固定文案(按钮/标题/提示)
UI_TEXT = (
    '小月饼的足迹地图 王斯卯 岁半 走四方 '
    '个足迹点 省份 直辖市 全打卡 邻省 成就 随机旅程 音乐 '
    '足迹中国 旅程重放 城市墙 点击联动地图 按时间线 编辑 保存 导出数据 '
    '胶片 拖拽旋转 看照片 首访 照片 张 待补记忆 家 从这里出发 '
    '重置 缩放 加载中 地图加载中 地图数据加载失败 离线状态 右侧城市墙正常可用 '
    '随机 暂停 继续 停止重放 背景音乐 切换 '
    '年 月 日 第 共 已 未 完成 全部 更多 收起 展开 关闭 确定 取消 '
    '京津冀 河北 山东 山西 陕西 湖北 河南 内蒙古 贵州 四川 江西 福建 '
    '直辖市 自治区 省 市 县 区 '
    '个个 张张 次次 天天 '
    '0123456789%·—～·/-：: '
)
chars |= set(UI_TEXT)

# 1c. 常见标点与符号
chars |= set('，。！？、；""''（）《》【】·—…～%')

# 去掉空白字符
chars.discard(' ')
chars.discard('\n')
chars.discard('\t')

text = ''.join(sorted(chars))
print('需要子集化的字符数: %d' % len(text))
print('字符:', text)
print()

# ── 2. 子集化 ──
opts = subset.Options()
opts.layout_features = ['*']
opts.name_IDs = ['*']
opts.notdef_outline = True
opts.recalc_bounds = True
opts.drop_tables = ['DSIG']
opts.flavor = 'woff2'          # 直接输出 woff2

font = subset.load_font(SRC, opts)
ss = subset.Subsetter(options=opts)
ss.populate(text=text)
ss.subset(font)
subset.save_font(font, OUT, opts)

src_kb = os.path.getsize(SRC) / 1024
dst_kb = os.path.getsize(OUT) / 1024
print('原始 TTF:  %.0f KB' % src_kb)
print('子集 WOFF2: %.0f KB' % dst_kb)
print('压缩至:    %.1f%%' % (dst_kb / src_kb * 100))
print()
print('输出:', OUT)
