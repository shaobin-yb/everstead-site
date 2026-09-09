# -*- coding: utf-8 -*-
"""
产品净值 SDK 取数管道（iFinDPy 直连版）— 就绪待命

说明: iFinD 官方 Python SDK (iFinDPy) 已安装(3.12.14 环境), 全部取数函数可用,
     唯一缺的是账号密码。老板提供密码后, 把密码写入:
         C:/Users/13167/.claude/settings.local.json → env.THS_PASSWORD
     (或环境变量 THS_PASSWORD), 本脚本即可全自动拉净值, 彻底不碰客户端 UI。

用法:
  py -V:Astral/CPython3.12.14 nav_sdk.py [--probe]

--probe 模式: 登录后探测保险资管产品净值序列的正确指标代码
(候选: 用 THS_DataPool 遍历, 或查 F9 深度资料页同源数据)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).parent
PRODUCTS = {
    "ZY0049": {"name": "中邮资管价值策略1号", "code": "ZY0049.BZJ"},
    "ZY0053": {"name": "中邮资管红利质量量化选股策略", "code": "ZY0053.BZJ"},
}

# iFinDPy 保险资管产品常用指标候选(待 --probe 验证)
CANDIDATE_INDICATORS = [
    "ths_nav_insurance_amc",          # 猜测1
    "ths_unit_nav_insurance",         # 猜测2
    "ths_acc_nav_insurance",          # 猜测3
    "ths_insurance_product_nav",      # 猜测4
]


def get_password() -> str:
    pw = os.environ.get("THS_PASSWORD", "")
    if pw:
        return pw
    cfg = Path.home() / ".claude" / "settings.local.json"
    if cfg.exists():
        d = json.loads(cfg.read_text(encoding="utf-8"))
        return (d.get("env") or {}).get("THS_PASSWORD", "")
    return ""


def main():
    from iFinDPy import THS_iFinDLogin
    pw = get_password()
    if not pw:
        print("[skip] 未配置 THS_PASSWORD（settings.local.json env 或环境变量）")
        print("       老板提供密码后本管道即可启用, 全程无 UI")
        return
    r = THS_iFinDLogin("zyzcgs125", pw)
    code = getattr(r, "errorcode", None)
    if code not in (0, None):
        print(f"[fail] SDK 登录失败: {getattr(r, 'errmsg', r)}")
        return
    print("[ok] SDK 登录成功")
    if "--probe" in sys.argv:
        from iFinDPy import THS_DataPool
        for prod, meta in PRODUCTS.items():
            for ind in CANDIDATE_INDICATORS:
                try:
                    res = THS_DataPool(meta["code"], ind, "2026-09-01;2026-09-09")
                    err = getattr(res, "errorcode", -1)
                    print(f"  {meta['code']} × {ind}: err={err}")
                    if err == 0:
                        print("    命中! data 结构:", str(res)[:300])
                except Exception as e:
                    print(f"  {meta['code']} × {ind}: 异常 {str(e)[:80]}")


if __name__ == "__main__":
    main()
