# -*- coding: utf-8 -*-
"""用真实结构的样本验证 Nuxt2Payload 解析是否正确。"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nuxt2_payload import Nuxt2Payload  # noqa: E402

# 一个结构跟真实站点一致的脱敏样本（数据都是假的）
SAMPLE = '''<!DOCTYPE html><html><head><title>t</title></head><body>
<script>window.__NUXT__=(function(a,b,c,d,e,f,g,h,i,j,k,l,m){return {layout:"default",data:[{searchWords:"",page:1,pageSize:10,goodsList:[{goodsNo:"TEST001",goodsUnionNo:a,gameId:e,gameIdName:f,goodsCatalogueId:g,goodsCatalogueIdName:h,goodsImg:"https://example.com/1.png",title:"Lv150，皮肤总价值120000，钻石I，总皮肤88",subtitle:"可二次实名",simpleMessage:a,viewsNum:1234,price:i,merchantMark:a,compensation:d,top:d,createTime:"2026-01-01 10:00:00",onStandTime:"2026-01-01 10:05:00",label1:a},{goodsNo:"TEST002",goodsUnionNo:a,gameId:e,gameIdName:f,goodsCatalogueId:g,goodsCatalogueIdName:h,goodsImg:"https://example.com/2.png",title:"Lv80，皮肤总价值20000，白银II，总皮肤12",subtitle:a,simpleMessage:a,viewsNum:56,price:j,createTime:"2026-01-01 09:00:00",onStandTime:"2026-01-01 09:01:00",label1:a}],gameName:f,hasCurrentGame:c}],fetch:{},error:d,state:{},serverRendered:c,routePath:"/goodsList/231/6",config:{}}}(null,"x",true,null,231,"无畏契约",6,"成品号",1999,888,true,1,2))</script>
</body></html>'''

p = Nuxt2Payload(SAMPLE)
print("解析状态:", p)
print("顶层 keys:", p.keys())
print()

checks = [
    ("gameName", p.get("data.0.gameName"), "无畏契约"),
    ("第1条 goodsNo", p.get("data.0.goodsList.0.goodsNo"), "TEST001"),
    ("第1条 price", p.get("data.0.goodsList.0.price"), 1999),
    ("第1条 gameId", p.get("data.0.goodsList.0.gameId"), 231),
    ("第1条 gameIdName", p.get("data.0.goodsList.0.gameIdName"), "无畏契约"),
    ("第1条 分类名", p.get("data.0.goodsList.0.goodsCatalogueIdName"), "成品号"),
    ("第1条 上架时间", p.get("data.0.goodsList.0.onStandTime"), "2026-01-01 10:05:00"),
    ("第1条 viewsNum", p.get("data.0.goodsList.0.viewsNum"), 1234),
    ("第1条 subtitle", p.get("data.0.goodsList.0.subtitle"), "可二次实名"),
    ("第2条 price", p.get("data.0.goodsList.1.price"), 888),
    ("第2条 title", p.get("data.0.goodsList.1.title"), "Lv80，皮肤总价值20000，白银II，总皮肤12"),
    ("serverRendered(bool)", p.get("serverRendered"), True),
    ("null 字段", p.get("data.0.goodsList.0.merchantMark"), None),
]

ok = 0
for name, got, want in checks:
    good = got == want
    ok += 1 if good else 0
    print("  [%s] %-22s -> %r" % ("OK" if good else "FAIL", name, got))

print()
print("goodsList 条数:", len(p.section("data.0.goodsList")))
print("第一条 goodsNo（first）:", (p.first("data.0.goodsList") or {}).get("goodsNo"))
print()
print("通过 %d / %d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
