# -*- coding: utf-8 -*-
"""验证盼之适配器（用脱敏样本，不联网）。"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from adapters import pzds  # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "pzds_list.html")
DETAIL = os.path.join(HERE, "fixtures", "pzds_detail.html")


def main():
    ok = fail = 0

    def check(name, got, want):
        nonlocal ok, fail
        good = got == want
        if good:
            ok += 1
        else:
            fail += 1
        print("  [%s] %-26s -> %r" % ("OK" if good else "FAIL", name, got))

    print("=== 列表页 ===")
    html = io.open(SAMPLE, encoding="utf-8").read()
    res = pzds.parse_list_page(html)
    check("game_name", res["game_name"], "无畏契约")
    check("条数", len(res["goods"]), 2)
    g0 = res["goods"][0]
    check("goods_no", g0["goods_no"], "TEST001")
    check("price", g0["price"], 1999)
    check("title", g0["title"], "Lv150，皮肤总价值120000，钻石I，总皮肤88")
    check("on_stand_time", g0["on_stand_time"], "2026-01-01 10:05:00")
    check("views_num", g0["views_num"], 1234)
    check("goods_img", g0["goods_img"], "https://example.com/1.png")
    check("第二条 price", res["goods"][1]["price"], 888)

    print("\n=== 详情页 ===")
    dhtml = io.open(DETAIL, encoding="utf-8").read()
    d = pzds.parse_detail_page(dhtml)
    check("goods_no", d["goods_no"], "TEST001")
    check("status", d["status"], "ON_STAND")
    check("status_name", d["status_name"], "在售")
    check("price", d["price"], 1999)
    check("game_name", d["game_name"], "无畏契约")

    print("\n=== 链接拼接 ===")
    check("带分类", pzds.goods_url("TEST001", 6),
          "https://www.pzds.com/goodsDetails/TEST001/6?click_location=buyer_share")
    check("无分类", pzds.goods_url("TEST001", None),
          "https://www.pzds.com/goodsDetails/TEST001")

    print("\n通过 %d / %d" % (ok, ok + fail))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
