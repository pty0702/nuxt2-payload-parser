# -*- coding: utf-8 -*-
"""示例适配器：盼之代售（www.pzds.com）商品列表 / 详情页。

它演示了怎么在通用解析器之上，用几行代码把一个具体站点的字段映射出来。
换别的 Nuxt2 站点时，照抄这个文件的形状，把路径和字段名改掉即可。
"""
from nuxt2_payload import Nuxt2Payload

# 详情页状态码 -> 中文
STATUS_TEXT = {
    "ON_STAND": "在售",
    "SOLD": "已售出",
    "ITEM_SOLD": "已售出",
    "TRADING": "交易中",
    "DOWN_STAND": "已下架",
    "ONESELF_DOWN_STAND": "卖家下架",
    "FORCE_DOWN_STAND": "强制下架",
    "VERIFY_FAIL": "审核未过",
    "WAIT_PUBLISH": "待发布",
    "ITEM_REMOVED": "已删除",
}

_LIST_FIELDS = {
    "goods_no": "goodsNo",
    "title": "title",
    "subtitle": "subtitle",
    "price": "price",
    "goods_img": "goodsImg",
    "views_num": "viewsNum",
    "create_time": "createTime",
    "on_stand_time": "onStandTime",
}


def parse_list_page(html):
    """解析商品列表页。

    返回::

        {"game_name": str|None,
         "goods": [{"goods_no":..., "title":..., "price":..., ...}, ...]}
    """
    p = Nuxt2Payload(html)
    items = p.section("data.0.goodsList")
    goods = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        goods_no = item.get("goodsNo")
        if not goods_no or goods_no in seen:
            continue
        seen.add(goods_no)
        row = {}
        for key, field in _LIST_FIELDS.items():
            value = item.get(field)
            row[key] = value if value is not None else ("" if key != "price" else None)
        goods.append(row)
    return {"game_name": p.get("data.0.gameName"), "goods": goods}


_DETAIL_FIELDS = {
    "goods_no": "goodsNo",
    "title": "title",
    "status": "status",
    "status_name": "statusName",
    "price": "price",
    "goods_img": "goodsImg",
    "on_stand_time": "onStandTime",
    "create_time": "createTime",
    "transaction_time": "transactionTime",
    "pay_time": "payTime",
    "game_name": "gameIdName",
}


def parse_detail_page(html):
    """解析商品详情页（数据在 data.0.detailsData 下）。"""
    p = Nuxt2Payload(html)
    detail = p.section("data.0.detailsData", default={})
    out = {}
    for key, field in _DETAIL_FIELDS.items():
        value = detail.get(field) if isinstance(detail, dict) else None
        out[key] = value
    return out


def goods_url(goods_no, catalogue_id=None, base="https://www.pzds.com"):
    """商品链接。

    带分类段的格式在手机端才会被正确识别（www 会 301 到 m7，路径段要保留）：
        {base}/goodsDetails/{goodsNo}/{catalogueId}?click_location=buyer_share
    没有 catalogueId 时回退到短链接。
    """
    goods_no = (goods_no or "").strip()
    try:
        cat = int(catalogue_id) if catalogue_id not in (None, "", 0) else None
    except (TypeError, ValueError):
        cat = None
    if goods_no and cat:
        return "%s/goodsDetails/%s/%d?click_location=buyer_share" % (base, goods_no, cat)
    return "%s/goodsDetails/%s" % (base, goods_no)
