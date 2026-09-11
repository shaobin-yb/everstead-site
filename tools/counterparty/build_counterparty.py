# -*- coding: utf-8 -*-
"""
直接交易对手库 → 成果站工具箱页面生成器
数据源: D:\\工作文件\\初期项目\\方案等文件\\直接交易对手库汇总表20241223-更新地域.xlsx
输出:   counterparty.html (数据内嵌, 零外部依赖)

分类体系 (2026-09-11 版):
  分类  金融同业 / 城投平台 / 产业企业 / 综合集团
  性质  央企 / 地方国企 / 其他(民企及混合股权)

重新生成: py build_counterparty.py
Excel 更新后重跑本脚本即可刷新页面数据。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

SRC = Path(r"D:\工作文件\初期项目\方案等文件\直接交易对手库汇总表20241223-更新地域.xlsx")
OUT = Path(__file__).parent / "counterparty.html"

# 汇总表 5 家缺注册省的企业, 按公开信息补全 (核实日期 2026-09-11)
PROV_FIX = {
    "国泰君安证券股份有限公司": "上海市",        # 601211.SH 注册地上海 (iFind)
    "绍兴市城市建设投资集团有限公司": "浙江省",
    "中航国际实业控股有限公司": "广东省",        # 注册地深圳市南山区 (简式权益变动报告书)
    "唐山冀东水泥股份有限公司": "河北省",        # 000401.SZ 注册地河北 (iFind)
    "宁波市北仑区国有资本运营有限公司": "浙江省",
}

RATING_ORDER = {"AAA": 12, "AA+": 11, "AA": 10, "AA-": 9, "A+": 8, "A": 7, "A-": 6,
                "BBB+": 5, "BBB": 4, "BBB-": 3, "BB+": 2, "BB": 1, "B+": 0}
RATING_SET = set(RATING_ORDER)

# ============================================================
# 分类器: 手工校准优先, 其次关键词规则(金融→城投→产业), 兜底综合集团
# 规则基于 468 家全量名单逐家核对 (2026-09-11)
# ============================================================

# 纯关键词会误判的点名纠正 (名称→分类)
MANUAL_CAT = {
    # --- 金融同业 ---
    "中央汇金投资有限责任公司": "金融同业",
    "中国中信有限公司": "金融同业",
    "中国中信集团有限公司": "金融同业",
    "中国光大集团股份公司": "金融同业",
    "中国国际金融股份有限公司": "金融同业",      # 中金公司, 名称无"证券"二字
    "上海国际集团有限公司": "金融同业",          # 上海市属金融控股平台
    "南京紫金投资集团有限责任公司": "金融同业",   # 南京金控
    "广东粤财投资控股有限公司": "金融同业",       # 粤财 AMC/信托/担保
    "山东省鲁信投资控股集团有限公司": "金融同业", # 鲁信信托金控
    "山东省财金投资集团有限公司": "金融同业",     # 山东政府引导基金平台
    "厦门金圆投资集团有限公司": "金融同业",       # 厦门市属金融投资平台
    "三峡资本控股有限责任公司": "金融同业",       # 三峡集团金融投资平台
    "深圳市创新投资集团有限公司": "金融同业",     # 深创投
    # --- 城投平台 ---
    "四川发展(控股)有限责任公司": "城投平台",
    "四川省投资集团有限责任公司": "城投平台",
    "蜀道投资集团有限责任公司": "城投平台",       # 四川公路铁路投资平台
    "四川省港航投资集团有限责任公司": "城投平台",
    "宜宾发展控股集团有限公司": "城投平台",
    "成都兴城投资集团有限公司": "城投平台",
    "中国雄安集团有限公司": "城投平台",           # 雄安新区开发平台
    "中原豫资投资控股集团有限公司": "城投平台",   # 河南省属平台
    "青岛国信发展(集团)有限责任公司": "城投平台",
    "宁波通商控股集团有限公司": "城投平台",
    "宁波市鄞开投资集团有限责任公司": "城投平台",
    "漳州市九龙江集团有限公司": "城投平台",
    "福州左海控股集团有限公司": "城投平台",
    "重庆渝富控股集团有限公司": "城投平台",       # 重庆国资运营
    "重庆城市交通开发投资(集团)有限公司": "城投平台",
    "北京金融街投资(集团)有限公司": "城投平台",   # 西城区国资平台
    "北京亦庄投资控股有限公司": "城投平台",       # 亦庄经开区平台
    "上海浦东发展(集团)有限公司": "城投平台",     # 浦发集团
    "上海张江(集团)有限公司": "城投平台",
    "上海临港经济发展(集团)有限公司": "城投平台",
    "上海陆家嘴金融贸易区开发股份有限公司": "城投平台",
    # --- 产业企业 ---
    "中国交通建设集团有限公司": "产业企业",       # 央企建筑, 防止"交通建设"误判城投
    "中国交通建设股份有限公司": "产业企业",
    "中国中铁股份有限公司": "产业企业",
    "中国铁建股份有限公司": "产业企业",
    "中国葛洲坝集团有限公司": "产业企业",
    "中国冶金科工股份有限公司": "产业企业",
    "中国五矿集团有限公司": "产业企业",
    "中国长江三峡集团有限公司": "产业企业",
    "中国东方电气集团有限公司": "产业企业",
    "中国中车集团有限公司": "产业企业",
    "中国华能集团有限公司": "产业企业",           # 五大发电集团总部, 名称无行业词
    "中国大唐集团有限公司": "产业企业",
    "中国华电集团有限公司": "产业企业",
    "中国北方工业有限公司": "产业企业",           # 兵器工业系军贸公司
    "中国巨石股份有限公司": "产业企业",           # 玻纤制造(中建材系)
    "中国中化股份有限公司": "产业企业",
    "先正达集团股份有限公司": "产业企业",
    "国药控股股份有限公司": "产业企业",
    "广州医药集团有限公司": "产业企业",
    "招商局蛇口工业区控股股份有限公司": "产业企业",
    "华侨城集团有限公司": "产业企业",
    "深圳华侨城股份有限公司": "产业企业",
    "中建国际投资集团有限公司": "产业企业",
    "中海企业发展集团有限公司": "产业企业",       # 中海地产
    "保利发展控股集团股份有限公司": "产业企业",
    "大悦城控股集团股份有限公司": "产业企业",
    "金融街控股股份有限公司": "产业企业",
    "北京城建投资发展股份有限公司": "产业企业",   # 地产上市公司, 防止"城建"误判城投
    "中航国际实业控股有限公司": "产业企业",       # 中航工业产业投资公司
    "新兴际华集团有限公司": "产业企业",
    "北京金隅集团股份有限公司": "产业企业",
    "申能(集团)有限公司": "产业企业",
    "中核汇能有限公司": "产业企业",
    "广州发展集团股份有限公司": "产业企业",       # 综合能源上市公司, 防止"发展集团"误判城投
    "深业集团有限公司": "产业企业",
    "江苏洋河集团有限公司": "产业企业",
    "泸州老窖集团有限责任公司": "产业企业",
    "北京首都创业集团有限公司": "综合集团",       # 首创: 水务+地产+环保
    "上海上实(集团)有限公司": "综合集团",
    "上海久事(集团)有限公司": "综合集团",
    "上海国盛(集团)有限公司": "综合集团",
    "中国通用技术(集团)控股有限责任公司": "综合集团",
    "中国诚通控股集团有限公司": "综合集团",
    "中国国新控股有限责任公司": "综合集团",
    "国家开发投资集团有限公司": "综合集团",
    "中国邮政集团有限公司": "综合集团",
    "招商局集团有限公司": "综合集团",
    "华润股份有限公司": "综合集团",
    "厦门建发集团有限公司": "综合集团",
    "厦门建发股份有限公司": "综合集团",
    "珠海华发集团有限公司": "综合集团",
    "江苏省国信集团有限公司": "综合集团",
    "陕西投资集团有限公司": "综合集团",
    "无锡市国联发展(集团)有限公司": "综合集团",
    "烟台国丰投资控股集团有限公司": "综合集团",
    "广东恒健投资控股有限公司": "综合集团",
    "广州越秀集团股份有限公司": "综合集团",
    "广东粤海控股集团有限公司": "综合集团",
    "浙江省国际贸易集团有限公司": "综合集团",
    "佛山市投资控股集团有限公司": "综合集团",
    "深圳市投资控股有限公司": "综合集团",
    "北京控股集团有限公司": "综合集团",
}

FIN_KW = ["银行", "证券", "保险", "信托", "租赁", "基金", "资产管理股份有限公司",
          "金融控股", "资本控股集团股份有限公司", "资本股份有限公司", "金控"]
LGFV_KW = ["城市建设", "城市发展", "城市投资", "城建", "城投", "建设投资", "建设发展",
           "交通投资", "交通建设", "交通控股", "交通集团", "交通发展", "交通产业",
           "交通基建", "轨道交通", "轨道建设", "地铁", "高速", "公路", "路桥",
           "水务", "水利投资", "市政", "基础设施", "新区", "园区", "开发区",
           "高新", "科技投资", "产业投资", "产业发展", "国资", "国有资本", "国有资产",
           "国有投资", "安居", "保障房", "综合发展", "发展集团", "发展投资",
           "兴城投资", "龙城发展", "太湖新城", "知识城", "资本运营", "投资开发"]
IND_KW = ["电力", "能源", "电网", "发电", "石油", "石化", "化工", "燃气", "风电", "水电", "核电",
          "核工业", "核能", "广核", "新能源", "煤", "钢", "矿业", "钢铁", "钢集团", "铝",
          "铜业", "有色", "黄金", "建材", "水泥", "建筑", "建工", "工程局", "地产",
          "置地", "置业", "汽车", "医药", "食品", "航空", "航天", "机场", "铁路",
          "港口", "港集团", "港股份", "港务", "海运", "远洋", "航运", "油田", "重工",
          "机械", "装备", "兵器", "科技集团", "信息通信", "传媒", "数字电视", "出版",
          "旅游", "环保", "节能", "环境", "特钢"]


def classify(name: str) -> str:
    if name in MANUAL_CAT:
        return MANUAL_CAT[name]
    for kw in FIN_KW:
        if kw in name:
            return "金融同业"
    for kw in LGFV_KW:
        if kw in name:
            return "城投平台"
    for kw in IND_KW:
        if kw in name:
            return "产业企业"
    return "综合集团"


# 央企系名单 (按集团归属判断, 含央企集团及其控股子公司, 2026-09-11)
CENTRAL = {
    "中央汇金投资有限责任公司", "中国国家铁路集团有限公司", "大秦铁路股份有限公司",
    "国家电网有限公司", "鲁能集团有限公司", "国网信息通信产业集团有限公司",
    "英大泰和人寿保险股份有限公司", "英大泰和财产保险股份有限公司",
    "中国石油天然气股份有限公司", "中国石油天然气集团有限公司",
    "中国石油化工股份有限公司", "中国石油化工集团有限公司",
    "中国海洋石油有限公司", "中海油田服务股份有限公司",
    "中国建筑股份有限公司", "中国建筑第八工程局有限公司",
    "中建国际投资集团有限公司", "中海企业发展集团有限公司",
    "中国建材股份有限公司", "中国建材集团有限公司", "中国巨石股份有限公司",
    "中国五矿集团有限公司", "中国冶金科工股份有限公司", "中国中车集团有限公司",
    "中国大唐集团有限公司", "大唐国际发电股份有限公司", "中国大唐集团新能源股份有限公司",
    "中国中煤能源股份有限公司", "中国中煤能源集团有限公司",
    "中国华能集团有限公司", "华能国际电力股份有限公司", "华能澜沧江水电股份有限公司",
    "华能新能源股份有限公司", "北方联合电力有限责任公司",
    "中国华电集团有限公司", "华电国际电力股份有限公司", "华电煤业集团有限公司",
    "华电新能源集团股份有限公司",
    "国家能源投资集团有限责任公司", "龙源电力集团股份有限公司", "国电电力发展股份有限公司",
    "国家电力投资集团有限公司", "上海电力股份有限公司", "电投融和新能源发展有限公司",
    "中国长江三峡集团有限公司", "中国长江电力股份有限公司",
    "中国三峡新能源(集团)股份有限公司", "三峡资本控股有限责任公司",
    "雅砻江流域水电开发有限公司",
    "中国核工业集团有限公司", "中国核能电力股份有限公司", "中国核工业建设股份有限公司",
    "中核汇能有限公司",
    "中国广核集团有限公司", "中国广核电力股份有限公司", "中广核风电有限公司",
    "中国南方电网有限责任公司",
    "国家开发投资集团有限公司", "国投电力控股股份有限公司",
    "国投资本股份有限公司", "国投证券股份有限公司",
    "中国诚通控股集团有限公司", "中国国新控股有限责任公司",
    "招商局集团有限公司", "招商银行股份有限公司", "招商证券股份有限公司",
    "招商局蛇口工业区控股股份有限公司", "招商局港口集团股份有限公司",
    "招商局公路网络科技控股股份有限公司",
    "华润股份有限公司", "华润置地控股有限公司", "华润医药控股有限公司",
    "中国中信有限公司", "中国中信集团有限公司", "中信银行股份有限公司",
    "中信证券股份有限公司", "中信建投证券股份有限公司", "中信保诚人寿保险有限公司",
    "中信泰富特钢集团股份有限公司",
    "中国光大集团股份公司", "中国光大银行股份有限公司", "光大证券股份有限公司",
    "光大永明人寿保险有限公司",
    "中国旅游集团有限公司", "中国东方资产管理股份有限公司", "中国信达资产管理股份有限公司",
    "中国航空工业集团有限公司", "中航国际实业控股有限公司", "中航国际融资租赁有限公司",
    "中国航空集团有限公司", "中国东方航空股份有限公司", "中国南方航空股份有限公司",
    "中国兵器工业集团有限公司", "中国北方工业有限公司", "中国兵器装备集团有限公司",
    "中国航天科技集团有限公司", "中国电子科技集团有限公司",
    "中国机械工业集团有限公司", "中国信息通信科技集团有限公司",
    "中国东方电气集团有限公司", "中国节能环保集团有限公司",
    "中国有色矿业集团有限公司", "中国铜业有限公司",
    "中国铝业集团有限公司", "中国铝业股份有限公司",
    "中国中化股份有限公司", "中化能源股份有限公司", "先正达集团股份有限公司",
    "中国远洋海运集团有限公司", "中远海运发展股份有限公司",
    "中国交通建设集团有限公司", "中国交通建设股份有限公司", "中交房地产集团有限公司",
    "中国中铁股份有限公司", "中国铁建股份有限公司",
    "中国电力建设股份有限公司", "中国能源建设股份有限公司", "中国葛洲坝集团有限公司",
    "中国宝武钢铁集团有限公司", "宝山钢铁股份有限公司",
    "新兴际华集团有限公司", "中国通用技术(集团)控股有限责任公司",
    "华侨城集团有限公司", "深圳华侨城股份有限公司",
    "中国邮政集团有限公司", "中国邮政储蓄银行股份有限公司",
    "中邮证券有限责任公司", "中邮人寿保险股份有限公司",
    "中国工商银行股份有限公司", "建信金融租赁有限公司", "建信人寿保险股份有限公司",
    "工银金融租赁有限公司", "工银安盛人寿保险有限公司",
    "中国建设银行股份有限公司",
    "中国农业银行股份有限公司", "农银人寿保险股份有限公司",
    "中国银行股份有限公司", "中银三星人寿保险有限公司",
    "交通银行股份有限公司", "交银金融租赁有限责任公司", "交银人寿保险有限公司",
    "中国财产再保险有限责任公司", "中国人寿再保险有限责任公司",
    "中国人寿保险股份有限公司", "中国人寿财产保险股份有限公司",
    "中国人民保险集团股份有限公司", "中国人民财产保险股份有限公司",
    "中国人民人寿保险股份有限公司",
    "太平财产保险有限公司", "太平人寿保险有限公司",
    "新华人寿保险股份有限公司", "中国国际金融股份有限公司",
    "中国银河证券股份有限公司", "申万宏源证券有限公司", "华商银行",
    "保利发展控股集团股份有限公司", "大悦城控股集团股份有限公司",
    "绿城房地产集团有限公司",   # 绿城中国大股东为中交集团
}

# 民企/混合股权 (其余默认为地方国企)
OTHER_NATURE = {
    "中国平安人寿保险股份有限公司", "中国平安财产保险股份有限公司",
    "平安银行股份有限公司", "平安国际融资租赁有限公司",
    "泰康保险集团股份有限公司", "泰康人寿保险有限责任公司",
    "泰康养老保险股份有限公司", "阳光人寿保险股份有限公司",
    "幸福人寿保险股份有限公司", "远东国际融资租赁有限公司",
    "厦门国际银行股份有限公司",
}


def nature_of(name: str) -> str:
    if name in CENTRAL:
        return "央企"
    if name in OTHER_NATURE:
        return "其他"
    return "地方国企"


def excel_date(v):
    if isinstance(v, (int, float)):
        return (datetime(1899, 12, 30) + timedelta(days=int(v))).strftime("%Y-%m-%d")
    return v or ""


def load():
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["汇总表"]
    active = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[0] is None:
            continue
        name = str(row[1]).strip()
        prov = str(row[2]).strip() if row[2] else ""
        prov = PROV_FIX.get(name, prov)
        active.append({
            "seq": int(row[0]),
            "name": name,
            "prov": prov,
            "cat": classify(name),
            "nature": nature_of(name),
            "ext": str(row[3] or "").strip(),
            "int": str(row[4] or "").strip(),
            "outlook": str(row[5] or "").strip(),
            "limit": row[6] if isinstance(row[6], (int, float)) else None,
            "date": excel_date(row[7]),
            "note": str(row[8]).strip() if row[8] else "",
            "analyst": str(row[9]).strip() if row[9] else "",
        })

    ws2 = wb["历史出库企业"]
    removed = []
    for row in ws2.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        int_raw = str(row[3]).strip() if row[3] else ""
        note = str(row[6]).strip() if row[6] else ""
        if int_raw not in RATING_SET:
            note = (int_raw + ";" + note) if note else int_raw
            int_raw = ""
        removed.append({
            "seq": int(row[0]),
            "name": str(row[1]).strip(),
            "ext": str(row[2] or "").strip(),
            "int": int_raw,
            "limit": row[4] if isinstance(row[4], (int, float)) else None,
            "date": excel_date(row[5]),
            "note": note,
        })
    return active, removed


HTML_TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>直接交易对手库 · EVERSTEAD</title>
<style>
:root{
  --bg:#03060c;
  --panel:rgba(10,20,38,.55);
  --panel-hover:rgba(14,28,52,.75);
  --line:rgba(56,189,248,.16);
  --line-strong:rgba(56,189,248,.45);
  --cyan:#22d3ee; --blue:#3b82f6; --violet:#8b5cf6;
  --green:#34d399; --orange:#fb923c; --rose:#f43f5e;
  --text:#e2ecf7; --muted:#7d92ad;
  --glow:0 0 24px rgba(34,211,238,.25);
  --mono:'JetBrains Mono','Cascadia Mono','Consolas','Courier New',ui-monospace,monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Microsoft YaHei','PingFang SC','Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit}
.bg-grid{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:radial-gradient(1100px 600px at 75% -10%,rgba(59,130,246,.16),transparent 60%),
    radial-gradient(900px 500px at -10% 110%,rgba(139,92,246,.12),transparent 60%),
    linear-gradient(rgba(56,189,248,.045) 1px,transparent 1px),
    linear-gradient(90deg,rgba(56,189,248,.045) 1px,transparent 1px),var(--bg);
  background-size:auto,auto,44px 44px,44px 44px,auto;
  mask-image:radial-gradient(ellipse 120% 90% at 50% 0%,#000 55%,transparent 100%);
  -webkit-mask-image:radial-gradient(ellipse 120% 90% at 50% 0%,#000 55%,transparent 100%)}
.wrap{position:relative;z-index:3;max-width:1240px;margin:0 auto;padding:0 24px 56px}

.topbar{display:flex;align-items:center;gap:14px;padding:22px 0 16px}
.topbar .logo{width:40px;height:40px;border-radius:10px;flex-shrink:0;background:linear-gradient(135deg,var(--cyan),var(--violet));display:flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;color:#03101f;box-shadow:var(--glow);font-family:var(--mono)}
.topbar .brand{font-family:var(--mono);font-weight:700;letter-spacing:.28em;font-size:15px}
.topbar .brand em{font-style:normal;background:linear-gradient(90deg,var(--cyan),var(--blue),var(--violet));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.topbar .back{margin-left:auto;font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 14px;background:rgba(10,20,38,.4);transition:border-color .25s,color .25s}
.topbar .back:hover{border-color:var(--line-strong);color:var(--cyan)}
.sub{font-family:var(--mono);font-size:12px;color:var(--muted);letter-spacing:.08em;padding:0 0 18px}

.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;backdrop-filter:blur(6px)}
.stat .k{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono)}
.stat .v{font-size:24px;font-weight:700;margin-top:4px;font-family:var(--mono)}
.stat .v small{font-size:12px;font-weight:400;color:var(--muted);margin-left:2px}
.stat .v.gold{color:var(--cyan)}
.stat .v.warn{color:var(--orange)}

/* 分类概览条 */
.cat-panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin-bottom:16px;backdrop-filter:blur(6px)}
.cat-panel .cat-title{font-size:11px;color:var(--muted);letter-spacing:.12em;font-family:var(--mono);margin-bottom:10px}
.cat-bar{display:flex;height:14px;border-radius:999px;overflow:hidden;margin-bottom:10px}
.cat-bar div{height:100%;transition:filter .2s}
.cat-bar div:hover{filter:brightness(1.3)}
.cat-legend{display:flex;flex-wrap:wrap;gap:8px 22px}
.cat-legend .lg{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:6px}
.cat-legend .dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.cat-legend b{color:var(--text);font-family:var(--mono);font-weight:600}
.cat-legend .lim{color:var(--cyan);font-family:var(--mono)}

.tabs{display:flex;gap:8px;margin-bottom:14px}
.tab{padding:9px 22px;border-radius:999px;border:1px solid var(--line);background:rgba(10,20,38,.4);color:var(--muted);cursor:pointer;font-size:13px;transition:all .2s;font-family:var(--mono);letter-spacing:.08em}
.tab:hover{border-color:var(--line-strong);color:var(--text)}
.tab.on{background:linear-gradient(135deg,rgba(34,211,238,.18),rgba(59,130,246,.18));border-color:var(--line-strong);color:var(--cyan)}
.tab .n{font-family:var(--mono);opacity:.75;margin-left:4px}

.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;align-items:center}
.toolbar input,.toolbar select{background:rgba(7,16,33,.95);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:8px 12px;font-size:13px;outline:none;transition:border-color .2s}
.toolbar input:focus,.toolbar select:focus{border-color:var(--line-strong)}
.toolbar input{flex:1;min-width:220px}
.toolbar select{cursor:pointer}
.toolbar select option{background:#0a1426}
.cnt{margin-left:auto;font-size:12px;color:var(--muted);font-family:var(--mono)}

.tbl-wrap{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:auto;max-height:72vh;backdrop-filter:blur(6px)}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:1020px}
thead th{position:sticky;top:0;background:rgba(7,16,33,.97);color:var(--muted);font-size:11px;font-weight:600;letter-spacing:.1em;padding:11px 12px;text-align:left;border-bottom:1px solid var(--line-strong);white-space:nowrap;font-family:var(--mono);z-index:2}
thead th.sort{cursor:pointer;user-select:none}
thead th.sort:hover{color:var(--cyan)}
thead th .dir{color:var(--cyan);margin-left:3px}
tbody td{padding:9px 12px;border-bottom:1px solid rgba(56,189,248,.07);white-space:nowrap}
tbody tr:hover{background:rgba(34,211,238,.05)}
tbody tr:nth-child(even){background:rgba(56,189,248,.025)}
td.name{font-weight:600}
td.mono{font-family:var(--mono)}
td.num{font-family:var(--mono);text-align:right}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-family:var(--mono);border:1px solid}
.b-ext{color:#7dd3fc;border-color:rgba(125,211,252,.3);background:rgba(125,211,252,.08)}
.b-int{color:#c4b5fd;border-color:rgba(196,181,253,.3);background:rgba(196,181,253,.08)}
.b-neg{color:var(--rose);border-color:rgba(244,63,94,.4);background:rgba(244,63,94,.1)}
.b-watch{color:var(--orange);border-color:rgba(251,146,60,.4);background:rgba(251,146,60,.1)}
.b-stable{color:#6ee7b7;border-color:rgba(110,231,183,.25);background:rgba(110,231,183,.07)}
.b-cat-fin{color:#c4b5fd;border-color:rgba(196,181,253,.35);background:rgba(196,181,253,.1)}
.b-cat-lgfv{color:#7dd3fc;border-color:rgba(125,211,252,.35);background:rgba(125,211,252,.1)}
.b-cat-ind{color:#6ee7b7;border-color:rgba(110,231,183,.35);background:rgba(110,231,183,.1)}
.b-cat-mix{color:#fdba74;border-color:rgba(251,146,60,.35);background:rgba(251,146,60,.1)}
.b-central{color:#f0abfc;border-color:rgba(240,171,252,.4);background:rgba(240,171,252,.1)}
.b-other{color:var(--orange);border-color:rgba(251,146,60,.4);background:rgba(251,146,60,.1)}
.note{color:var(--muted);font-size:12px;white-space:normal;max-width:340px;line-height:1.5}
.empty{padding:48px;text-align:center;color:var(--muted);font-size:13px}
.foot{margin-top:22px;font-size:11px;color:var(--muted);line-height:1.8;font-family:var(--mono);letter-spacing:.05em}

.gate{position:fixed;inset:0;z-index:99;background:rgba(3,6,12,.94);backdrop-filter:blur(10px);display:flex;align-items:center;justify-content:center}
.gate-panel{background:var(--panel);border:1px solid var(--line-strong);border-radius:16px;padding:38px 44px;box-shadow:0 12px 40px rgba(0,0,0,.25);width:min(400px,90vw);text-align:center}
.gate-panel .g-ico{font-size:34px;margin-bottom:12px}
.gate-panel h2{font-size:17px;letter-spacing:.2em;margin-bottom:6px}
.gate-panel p{font-size:12px;color:var(--muted);margin-bottom:20px}
.gate-panel input{width:100%;background:rgba(7,16,33,.95);border:1px solid var(--line);border-radius:8px;color:var(--text);padding:10px 14px;font-size:14px;outline:none;text-align:center;letter-spacing:.3em}
.gate-panel input:focus{border-color:var(--cyan)}
.gate-panel button{margin-top:14px;width:100%;padding:10px;border:none;border-radius:8px;background:linear-gradient(135deg,var(--cyan),var(--blue));color:#03101f;font-weight:700;font-size:14px;cursor:pointer;letter-spacing:.2em}
.gate-panel button:hover{filter:brightness(1.15)}
.gate.err .gate-panel{animation:shake .4s}
@keyframes shake{0%,100%{transform:translateX(0)}20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}
@media (max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="bg-grid"></div>

<div class="gate" id="gate">
  <div class="gate-panel">
    <div class="g-ico">🔒</div>
    <h2>直接交易对手库</h2>
    <p>内部授信评级数据 · 密码访问</p>
    <input type="password" id="pw" placeholder="请输入访问密码" autocomplete="off">
    <button id="btn">解 锁</button>
  </div>
</div>

<div class="wrap">
  <div class="topbar">
    <div class="logo">E</div>
    <div class="brand">EVERSTEAD <em>TOOLBOX</em></div>
    <a class="back" href="../../tools.html">← 工具箱</a>
  </div>
  <div class="sub">DIRECT COUNTERPARTY DATABASE · 中邮保险资产管理有限公司 · 更新于 2024-12-23</div>

  <div class="stats" id="stats"></div>
  <div class="cat-panel" id="catPanel"></div>

  <div class="tabs">
    <div class="tab on" id="tabActive" onclick="switchTab('active')">在库对手<span class="n" id="nActive"></span></div>
    <div class="tab" id="tabRemoved" onclick="switchTab('removed')">历史出库<span class="n" id="nRemoved"></span></div>
  </div>

  <div class="toolbar" id="toolbarActive">
    <input id="search" placeholder="🔍 搜索企业名称…">
    <select id="fCat"><option value="">全部分类</option></select>
    <select id="fProv"><option value="">全部省份</option></select>
    <select id="fExt"><option value="">全部外部评级</option></select>
    <select id="fInt"><option value="">全部内部评级</option></select>
    <select id="fOutlook"><option value="">全部展望</option></select>
    <select id="fNature"><option value="">全部性质</option></select>
    <select id="fAnalyst"><option value="">全部分析师</option></select>
    <span class="cnt" id="cnt"></span>
  </div>
  <div class="toolbar" id="toolbarRemoved" style="display:none">
    <input id="search2" placeholder="🔍 搜索出库企业名称…">
    <span class="cnt" id="cnt2"></span>
  </div>

  <div class="tbl-wrap" id="wrapActive"><table id="tblActive"></table></div>
  <div class="tbl-wrap" id="wrapRemoved" style="display:none"><table id="tblRemoved"></table></div>

  <div class="foot">
    数据源: 直接交易对手库汇总表20241223-更新地域.xlsx(汇总表 468 家 + 历史出库企业 58 家)<br>
    分类口径: 金融同业(银行/证券/保险/信托/租赁/AMC/金控/基金) · 城投平台(城建/交通/水务/园区/国资平台) · 产业企业(能源/制造/地产/建筑/运输) · 综合集团(多元混业控股)<br>
    性质口径: 央企(按集团归属判断, 含控股子公司) · 地方国企(默认) · 其他(民企及混合股权)<br>
    5 家缺注册省企业已按公开信息补全 · 授信额度单位: 亿元 · 内部评级 BB+ 及以下标橙、展望负面标红
  </div>
</div>

<script>
var ACTIVE = __ACTIVE__;
var REMOVED = __REMOVED__;
var RATING_ORDER = {"AAA":12,"AA+":11,"AA":10,"AA-":9,"A+":8,"A":7,"A-":6,"BBB+":5,"BBB":4,"BBB-":3,"BB+":2,"BB":1,"B+":0};
var CAT_COLOR = {"金融同业":"#8b5cf6","城投平台":"#22d3ee","产业企业":"#34d399","综合集团":"#fb923c"};
var LOW_INT = 2;
var curTab = 'active';
var sortKey = 'seq', sortDir = 1;

var PASSWORD_HASH = "62030069b40c02d1dd642d438194850f14d9e79a25abd1e53c02f7391f8242c8";
var GATE_KEY = 'cp_counterparty_ok';
function sha256(ascii){function rightRotate(value,amount){return(value>>>amount)|(value<<(32-amount))}
var mathPow=Math.pow,maxWord=mathPow(2,32),result='',words=[],asciiBitLength=ascii.length*8,hash=sha256.h=sha256.h||[],k=sha256.k=sha256.k||[],primeCounter=k.length,isComposite={};
for(var candidate=2;primeCounter<64;candidate++){if(!isComposite[candidate]){for(var i=0;i<313;i+=candidate)isComposite[i]=candidate;hash[primeCounter]=(mathPow(candidate,.5)*maxWord)|0;k[primeCounter++]=(mathPow(candidate,1/3)*maxWord)|0}}
ascii+='\x80';while(ascii.length%64-56)ascii+='\x00';
for(var i=0;i<ascii.length;i++){var j=ascii.charCodeAt(i);if(j>>8)return'';words[i>>2]|=j<<((3-i)%4)*8}
words[words.length]=((asciiBitLength/maxWord)|0);words[words.length]=(asciiBitLength);
for(var j=0;j<words.length;){var w=words.slice(j,j+=16),oldHash=hash;hash=hash.slice(0,8);
for(var i=0;i<64;i++){var w15=w[i-15],w2=w[i-2],a=hash[0],e=hash[4];
var temp1=hash[7]+(rightRotate(e,6)^rightRotate(e,11)^rightRotate(e,25))+((e&hash[5])^((~e)&hash[6]))+k[i]+(w[i]=(i<16)?w[i]:(w[i-16]+(rightRotate(w15,7)^rightRotate(w15,18)^(w15>>>3))+w[i-7]+(rightRotate(w2,17)^rightRotate(w2,19)^(w2>>>10)))|0);
var temp2=(rightRotate(a,2)^rightRotate(a,13)^rightRotate(a,22))+((a&hash[1])^(a&hash[2])^(hash[1]&hash[2]));
hash=[(temp1+temp2)|0].concat(hash);hash[4]=(hash[4]+temp1)|0}
for(var i=0;i<8;i++)hash[i]=(hash[i]+oldHash[i])|0}
for(var i=0;i<8;i++){for(var j=3;j+1;j--){var b=(hash[i]>>(j*8))&255;result+=((b<16)?0:'')+b.toString(16)}}
return result}
function unlock(){var gate=document.getElementById('gate'),input=document.getElementById('pw');
if(sha256(input.value)===PASSWORD_HASH){sessionStorage.setItem(GATE_KEY,'1');gate.style.display='none'}
else{gate.classList.remove('err');void gate.offsetWidth;gate.classList.add('err');input.value='';input.focus()}}
if(sessionStorage.getItem(GATE_KEY)==='1'){document.getElementById('gate').style.display='none'}

function statBox(k,v,unit,cls){return '<div class="stat"><div class="k">'+k+'</div><div class="v '+cls+'">'+v+'<small>'+unit+'</small></div></div>'}

function renderStats(){
  var total=0, aaa=0, warn=0;
  var cats={}, nat={};
  ACTIVE.forEach(function(c){
    total+=c.limit||0;
    if(c.ext==='AAA')aaa++;
    if(RATING_ORDER[c.int]!==undefined&&RATING_ORDER[c.int]<=LOW_INT)warn++;
    cats[c.cat]=(cats[c.cat]||0)+1;
    nat[c.nature]=(nat[c.nature]||0)+1;
  });
  var neg=ACTIVE.filter(function(c){return c.outlook.indexOf('负面')>=0}).length;
  var obs=ACTIVE.filter(function(c){return c.outlook.indexOf('观察')>=0}).length;
  var cent=ACTIVE.filter(function(c){return c.nature==='央企'});
  var centLim=0; cent.forEach(function(c){centLim+=c.limit||0});
  document.getElementById('stats').innerHTML=
    statBox('在库对手', ACTIVE.length, '家', '')+
    statBox('授信总额度', total, '亿元', 'gold')+
    statBox('央企系', cent.length, '家 · '+centLim+'亿', '')+
    statBox('覆盖省份', Object.keys(ACTIVE.reduce(function(m,c){m[c.prov]=1;return m},{})).length, '个省市自治区', '')+
    statBox('风险提示', (neg+obs)+warn, '负面'+neg+' · 观察'+obs+' · 低内评'+warn, 'warn');
  var catsN=0; ACTIVE.forEach(function(c){catsN+=c.limit||0});
  var order=['金融同业','城投平台','产业企业','综合集团'];
  var bar='', legend='';
  order.forEach(function(k){
    var n=cats[k]||0;
    if(!n)return;
    var lim=0; ACTIVE.forEach(function(c){if(c.cat===k)lim+=c.limit||0});
    var pct=Math.round(n/ACTIVE.length*1000)/10;
    var lpct=catsN?Math.round(lim/catsN*1000)/10:0;
    bar+='<div style="width:'+pct+'%;background:'+CAT_COLOR[k]+'" title="'+k+' '+n+'家 · '+lim+'亿"></div>';
    legend+='<span class="lg"><span class="dot" style="background:'+CAT_COLOR[k]+'"></span>'+k+' <b>'+n+'</b>家 <span class="lim">'+lim+'亿</span> ('+lpct+'%)</span>';
  });
  var otherN=nat['其他']||0, lgovN=nat['地方国企']||0;
  legend+='<span class="lg">｜ 央企 <b>'+cent.length+'</b>家 <span class="lim">'+centLim+'亿</span> · 地方国企 <b>'+lgovN+'</b>家 · 其他 <b>'+otherN+'</b>家</span>';
  document.getElementById('catPanel').innerHTML=
    '<div class="cat-title">CLASS BREAKDOWN · 分类概览(按授信额度占比加权)</div>'+
    '<div class="cat-bar">'+bar+'</div>'+
    '<div class="cat-legend">'+legend+'</div>';
}

function escapeHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function outBadge(c){return c.outlook==='负面'?'<span class="badge b-neg">负面</span>':(c.outlook.indexOf('观察')>=0?'<span class="badge b-watch">'+c.outlook+'</span>':(c.outlook==='稳定'?'<span class="badge b-stable">稳定</span>':escapeHtml(c.outlook)))}
function intBadge(c){var r=c.int;if(!r)return'—';var low=RATING_ORDER[r]!==undefined&&RATING_ORDER[r]<=LOW_INT;return'<span class="badge '+(low?'b-watch':'b-int')+'">'+r+'</span>'}
function catBadge(c){var cls={'金融同业':'b-cat-fin','城投平台':'b-cat-lgfv','产业企业':'b-cat-ind','综合集团':'b-cat-mix'}[c.cat]||'b-int';return'<span class="badge '+cls+'">'+escapeHtml(c.cat)+'</span>'}
function natBadge(c){if(c.nature==='央企')return'<span class="badge b-central">央企</span>';if(c.nature==='其他')return'<span class="badge b-other">其他</span>';return''}
function th(label,key){var dir=sortKey===key?'<span class="dir">'+(sortDir>0?'▲':'▼')+'</span>':'';return'<th class="'+(key?'sort':'')+'" '+(key?'data-sort="'+key+'" onclick="setSort(\''+key+'\')"':'')+'>'+label+dir+'</th>'}
function valOf(c,key){
  if(key==='seq')return c.seq;
  if(key==='name')return c.name;
  if(key==='prov')return c.prov;
  if(key==='cat')return c.cat;
  if(key==='ext')return RATING_ORDER[c.ext]||0;
  if(key==='int')return RATING_ORDER[c.int]||0;
  if(key==='limit')return c.limit||0;
  if(key==='date')return c.date;
  if(key==='nature')return c.nature;
  return c.analyst||'';
}
function renderActive(){
  var q=document.getElementById('search').value.trim().toLowerCase();
  var fP=document.getElementById('fProv').value, fE=document.getElementById('fExt').value,
      fI=document.getElementById('fInt').value, fO=document.getElementById('fOutlook').value,
      fA=document.getElementById('fAnalyst').value, fC=document.getElementById('fCat').value,
      fN=document.getElementById('fNature').value;
  var rows=ACTIVE.filter(function(c){
    if(q&&c.name.toLowerCase().indexOf(q)<0)return false;
    if(fC&&c.cat!==fC)return false;
    if(fP&&c.prov!==fP)return false;
    if(fE&&c.ext!==fE)return false;
    if(fI&&c.int!==fI)return false;
    if(fO&&c.outlook!==fO)return false;
    if(fN&&c.nature!==fN)return false;
    if(fA&&c.analyst!==fA)return false;
    return true;
  });
  rows.sort(function(a,b){var va=valOf(a,sortKey),vb=valOf(b,sortKey);if(va<vb)return -1*sortDir;if(va>vb)return 1*sortDir;return a.seq-b.seq});
  var html='<thead><tr>'+
    th('序号','seq')+th('名称','name')+th('注册省','prov')+th('分类','cat')+
    th('外部评级','ext')+th('内部评级','int')+th('展望','')+th('授信额度','limit')+
    th('最新评级日期','date')+th('备注','')+th('分析师','analyst')+'</tr></thead><tbody>';
  if(!rows.length)html+='<tr><td colspan="11" class="empty">无匹配结果</td></tr>';
  rows.forEach(function(c){
    html+='<tr><td class="mono">'+c.seq+'</td><td class="name">'+escapeHtml(c.name)+' '+natBadge(c)+'</td><td>'+escapeHtml(c.prov||'—')+'</td><td>'+catBadge(c)+'</td>'+
      '<td><span class="badge b-ext">'+escapeHtml(c.ext)+'</span></td><td>'+intBadge(c)+'</td><td>'+outBadge(c)+'</td>'+
      '<td class="num">'+(c.limit==null?'—':c.limit)+'</td><td class="mono">'+escapeHtml(c.date)+'</td>'+
      '<td class="note">'+escapeHtml(c.note||'—')+'</td><td>'+escapeHtml(c.analyst||'—')+'</td></tr>';
  });
  html+='</tbody>';
  document.getElementById('tblActive').innerHTML=html;
  document.getElementById('cnt').textContent='显示 '+rows.length+' / '+ACTIVE.length+' 家';
}
function renderRemoved(){
  var q=document.getElementById('search2').value.trim().toLowerCase();
  var rows=REMOVED.filter(function(c){return!q||c.name.toLowerCase().indexOf(q)>=0});
  var html='<thead><tr>'+
    th('序号','')+th('名称','')+th('外部评级','')+th('内部评级','')+th('原授信额度','')+th('最新评审日期','')+th('出库原因/备注','')+'</tr></thead><tbody>';
  if(!rows.length)html+='<tr><td colspan="7" class="empty">无匹配结果</td></tr>';
  rows.forEach(function(c){
    html+='<tr><td class="mono">'+c.seq+'</td><td class="name">'+escapeHtml(c.name)+'</td>'+
      '<td><span class="badge b-ext">'+escapeHtml(c.ext)+'</span></td><td>'+(c.int?'<span class="badge b-int">'+escapeHtml(c.int)+'</span>':'—')+'</td>'+
      '<td class="num">'+(c.limit==null?'—':c.limit)+'</td><td class="mono">'+escapeHtml(c.date)+'</td>'+
      '<td class="note">'+escapeHtml(c.note||'—')+'</td></tr>';
  });
  html+='</tbody>';
  document.getElementById('tblRemoved').innerHTML=html;
  document.getElementById('cnt2').textContent='显示 '+rows.length+' / '+REMOVED.length+' 家';
}
function setSort(key){if(sortKey===key){sortDir*=-1}else{sortKey=key;sortDir=1}renderActive()}
function switchTab(t){
  curTab=t;
  document.getElementById('tabActive').className='tab'+(t==='active'?' on':'');
  document.getElementById('tabRemoved').className='tab'+(t==='removed'?' on':'');
  document.getElementById('toolbarActive').style.display=t==='active'?'':'none';
  document.getElementById('toolbarRemoved').style.display=t==='removed'?'':'none';
  document.getElementById('wrapActive').style.display=t==='active'?'':'none';
  document.getElementById('wrapRemoved').style.display=t==='removed'?'':'none';
}
function fillSelect(id,vals,label){
  var sel=document.getElementById(id);
  sel.innerHTML='<option value="">'+label+'</option>';
  vals.forEach(function(v){sel.innerHTML+='<option value="'+escapeHtml(v)+'">'+escapeHtml(v)+'</option>'});
}
(function init(){
  document.getElementById('nActive').textContent=ACTIVE.length;
  document.getElementById('nRemoved').textContent=REMOVED.length;
  document.getElementById('btn').addEventListener('click',unlock);
  document.getElementById('pw').addEventListener('keydown',function(e){if(e.key==='Enter')unlock()});
  var provs=[],exts=[],ints=[],outs=[],anas=[],cats=[],nats=[];
  ACTIVE.forEach(function(c){
    if(c.prov&&provs.indexOf(c.prov)<0)provs.push(c.prov);
    if(c.ext&&exts.indexOf(c.ext)<0)exts.push(c.ext);
    if(c.int&&ints.indexOf(c.int)<0)ints.push(c.int);
    if(c.outlook&&outs.indexOf(c.outlook)<0)outs.push(c.outlook);
    if(c.analyst&&anas.indexOf(c.analyst)<0)anas.push(c.analyst);
    if(c.cat&&cats.indexOf(c.cat)<0)cats.push(c.cat);
    if(c.nature&&nats.indexOf(c.nature)<0)nats.push(c.nature);
  });
  ints.sort(function(a,b){return(RATING_ORDER[b]||0)-(RATING_ORDER[a]||0)});
  exts.sort(function(a,b){return(RATING_ORDER[b]||0)-(RATING_ORDER[a]||0)});
  provs.sort();anas.sort();
  var catOrder=['金融同业','城投平台','产业企业','综合集团'];
  cats.sort(function(a,b){return catOrder.indexOf(a)-catOrder.indexOf(b)});
  var natOrder=['央企','地方国企','其他'];
  nats.sort(function(a,b){return natOrder.indexOf(a)-natOrder.indexOf(b)});
  fillSelect('fCat',cats,'全部分类');
  fillSelect('fProv',provs,'全部省份');
  fillSelect('fExt',exts,'全部外部评级');
  fillSelect('fInt',ints,'全部内部评级');
  fillSelect('fOutlook',outs,'全部展望');
  fillSelect('fNature',nats,'全部性质');
  fillSelect('fAnalyst',anas,'全部分析师');
  ['search','fCat','fProv','fExt','fInt','fOutlook','fNature','fAnalyst'].forEach(function(id){document.getElementById(id).addEventListener('input',renderActive)});
  document.getElementById('search2').addEventListener('input',renderRemoved);
  renderStats();renderActive();renderRemoved();
})();
</script>
</body>
</html>
"""


def main():
    active, removed = load()
    print(f"在库 {len(active)} 家 | 出库 {len(removed)} 家")
    total = sum(c["limit"] for c in active if c["limit"] is not None)
    print(f"授信总额 {total} 亿元")

    from collections import Counter
    cats = Counter(c["cat"] for c in active)
    nats = Counter(c["nature"] for c in active)
    print("分类:", dict(cats))
    print("性质:", dict(nats))
    for c, n in cats.items():
        lim = sum(x["limit"] or 0 for x in active if x["cat"] == c)
        print(f"  {c}: {n} 家 / {lim} 亿元")
    for n, cnt in nats.items():
        lim = sum(x["limit"] or 0 for x in active if x["nature"] == n)
        print(f"  性质 {n}: {cnt} 家 / {lim} 亿元")

    missing = [c["name"] for c in active if not c["prov"]]
    if missing:
        print("⚠️ 仍有缺省份:", missing)

    html = (HTML_TPL
            .replace("__ACTIVE__", json.dumps(active, ensure_ascii=False))
            .replace("__REMOVED__", json.dumps(removed, ensure_ascii=False)))
    OUT.write_text(html, encoding="utf-8")
    print("已生成", OUT)


if __name__ == "__main__":
    main()
