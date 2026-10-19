# nuxt2-payload-parser

纯 Python 解析 **Nuxt2 SSR 页面内嵌的 `window.__NUXT__`**，把被压缩成函数形参引用的字段值（`price: f` 这种）还原成真实数据。

**不用 node、不用浏览器、不需要 selenium/playwright**，只要有 Python。

```
python -m pip install requests   # 唯一需要的外部依赖（仅示例用，解析本身零依赖）
```

---

## 一、它解决什么问题

Nuxt2 的 SSR 页面会把整页数据压进一个立即执行函数（IIFE），并把重复出现的值抽成**函数形参**来省体积：

```js
window.__NUXT__=(function(a,b,c,d,e,f){
    return {
      data:[{ goodsList:[
        { goodsNo:"PW2MGN2", price:f, gameId:a, gameIdName:b, title:"..." }
      ]}]
    }
}( 231, "无畏契约", true, null, 0, 1999 ))
   ↑ 形参列表                        ↑ 实参列表
```

`price:f` 里的 `f` 是第 6 个形参，对应第 6 个实参 `1999`。

**普通正则完全拿不到价格**——它只能看到字面量 `f`，看不懂 JavaScript 作用域。

本库做的事：

1. 切出 IIFE 的**形参名列表**和**实参文本列表**
2. 按位置一一对应，建立 `形参名 -> 实参值` 的映射表（`var_map`）
3. 用递归下降解析器把函数体转成 Python 对象，遇到标识符就查映射表
4. 提供按路径取值（`"data.0.goodsList.0.price"`）

---

## 二、快速开始

```python
from nuxt2_payload import Nuxt2Payload

html = open("page.html", encoding="utf-8").read()
p = Nuxt2Payload(html)

p.get("data.0.goodsList.0.goodsNo")   # -> "PW2MGN2"
p.get("data.0.goodsList.0.price")     # -> 1999      ← 被压缩成 f 的字段也能拿到
p.get("data.0.gameName")              # -> "无畏契约"

p.section("data.0.goodsList")         # -> [ {...}, {...} ]  整段列表
p.first("data.0.goodsList")           # -> 第一条
p.raw                                 # -> 整个 payload 字典
p.var_map                             # -> {"a": "231", "f": "1999", ...}
```

抓页面直接用 requests 就行：

```python
import requests
from nuxt2_payload import Nuxt2Payload

r = requests.get("https://example.com/goodsList/1/6", headers={"User-Agent": "Mozilla/5.0 ..."})
p = Nuxt2Payload(r.text)
print(p.get("data.0.goodsList"))
```

---

## 三、能解什么、解不了什么

| 情况 | 支持 |
|---|---|
| 字符串 / 数字 / 布尔 / null | ✅ |
| 对象、数组（任意嵌套） | ✅ |
| 被抽成形参的字段（`price:f`） | ✅ 核心能力 |
| 形参套形参（`price:f`，`f` 又是 `(1,2)` 的某个参数） | ✅ 递归查表（最多 8 层） |
| 字符串里的转义（`\u002F`、`\"`、`\n`） | ✅ |
| 函数体、运算表达式、三元表达式 | ❌ 返回 `None`（静态求不了） |
| 内联函数（`fn:function(){...}`） | ❌ `None`，但**不影响同一对象里的其它字段** |

> 解析是**容错**的：某个字段解不出来就跳过，不会让整页报废。

---

## 四、适配具体站点

`adapters/pzds.py` 是一个真实站点的示例（盼之代售），展示了怎么把通用解析器变成业务代码：

```python
from adapters import pzds

res = pzds.parse_list_page(html)
# {"game_name": "无畏契约",
#  "goods": [{"goods_no": "TEST001", "price": 1999, "title": "...", ...}, ...]}

detail = pzds.parse_detail_page(detail_html)
# {"goods_no": "TEST001", "status": "ON_STAND", "status_name": "在售", "price": 1999, ...}
```

换别的 Nuxt2 站点，照抄这个文件的形状，把字段路径改掉就行：

```python
def parse_list_page(html):
    p = Nuxt2Payload(html)
    items = p.section("data.0.goodsList")       # ← 改这里
    return [{"price": it.get("price")} for it in items]
```

---

## 五、跑测试

```bash
python tests/test_parse.py       # 通用解析器：13 项断言
python tests/test_adapters.py    # 盼之适配器 + 链接拼接：16 项断言
```

两个都是**离线**的，用 `tests/fixtures/` 里的脱敏样本，不联网、不含真实商品数据。

---

## 六、性能

在真实页面上（约 390 KB HTML、647 个形参）：

| 指标 | 数值 |
|---|---|
| 单页解析 | **约 0.1 秒** |
| 内存 | 单页 < 10 MB |
| 依赖 | 纯标准库 |

对比方案：

| 方案 | 依赖 | 速度 | 稳定性 |
|---|---|---|---|
| **本库（纯 Python）** | 无 | 0.1s | 高（不执行 JS） |
| node 执行 payload | node | 0.1s | 高 |
| Playwright / Selenium | 浏览器 | 2~5s | 受反爬影响 |
| 正则硬抠 | 无 | 快 | **拿不到被抽走的字段** |

---

## 七、目录结构

```
nuxt2-payload-parser/
├─ nuxt2_payload/__init__.py    通用解析引擎（Nuxt2Payload）
├─ adapters/pzds.py             示例适配：盼之代售
├─ tests/
│  ├─ test_parse.py             通用解析器测试
│  ├─ test_adapters.py          适配器测试
│  └─ fixtures/                 脱敏样本
├─ REVERSE-NOTES.md             实战逆向笔记（WAF、签名、分页、踩坑）
└─ README.md
```

---

## 八、许可

MIT。随便用，出问题别找我（但 issue 会看）。
