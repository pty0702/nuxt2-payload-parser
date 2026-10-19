# nuxt2-payload-parser

纯 Python 解析 **Nuxt2 SSR 页面内嵌的 `window.__NUXT__`**，把被压缩成函数形参引用的字段值（`price: f` 这种）还原成真实数据。

**不用 node、不用浏览器、不需要 selenium/playwright**，只要有 Python。

```
python -m pip install requests   # 唯一需要的外部依赖（仅示例用，解析本身零依赖）
```

---

## 零、应用场景（先看这个，判断你需不需要它）

### ✅ 适用：你的目标站点符合下面任意一条

| 场景 | 具体例子 |
|---|---|
| **商品/账号实时监控** | 盯某个交易平台的新上架、改价、售出，推到飞书/钉钉/邮箱 |
| **行情与选品分析** | 定期抓全站在售列表，算价格分布、性价比排行、哪些配置卖得贵 |
| **历史数据沉淀** | 每天存一份快照，跑了几周就能看「同配置号的成交价走势」 |
| **竞品/类目对比** | 抓多个分类（成品号、首充号、代练号）横向比价 |
| **内容站数据抓取** | 抓 Nuxt2 博客/资讯站的列表和正文，做聚合或 RSS |
| **SaaS 后台抓数** | 有些后台也是 Nuxt2 SSR，登录后页面里同样有 payload |

**判断方法（30 秒）**：打开目标页面 → `Ctrl+F` 搜 `window.__NUXT__`。
- 搜到 → ✅ 本库大概率直接能用
- 只搜到 `__NEXT_DATA__` → ❌ 那是 Next.js，换个库
- 搜到 `__INITIAL_STATE__` → ⚠️ 可能是 Nuxt3 / 其他框架，结构不同（可参考思路但要重写解析）
- 什么都没有 → ❌ 纯客户端渲染（CSR），得上浏览器

### ❌ 不适用：这些情况别浪费时间

| 情况 | 说明 | 该用什么 |
|---|---|---|
| 页面是纯 CSR（Vue/React 客户端渲染） | HTML 里没有数据，全在 JS 里异步拉 | Playwright / Selenium |
| 数据全靠 API + 强风控（WAF、签名、验证码） | 本库只解页面，不解风控 | 浏览器自动化，或逆向签名 |
| 需要登录态才有数据 | 本库只解析，不处理登录 | requests + 手动带 cookie，或浏览器 |
| 目标站点改版频繁 | 字段路径变了就要改适配器 | 加重试与告警，别硬扛 |

### 典型工作流（以账号交易监控为例）

```
定时抓列表页 HTML
   ↓  Nuxt2Payload 解出 goodsList（含被压缩的 price）
写进 SQLite，和上一轮比对
   ↓
新出现的 → 新上架
价格变了的 → 改价
从窗口消失的 → 回查详情页 status 判断成交/下架
   ↓
按规则筛选（价格区间 / 皮肤价值 / 性价比 / 关键词）
   ↓
推送（飞书机器人 / 邮件 / webhook）
```

本库负责的是**第一步里最难的那一环**：把 `price:f` 解成 `1999`。

### 不做什么（边界）

- ❌ 不发请求（抓页面你自己用 requests）
- ❌ 不处理登录、cookie、验证码
- ❌ 不绕 WAF、不逆签名
- ❌ 不解析 Next.js（`__NEXT_DATA__`）、不解析 Nuxt3

它就是一把螺丝刀：**把 Nuxt2 的 SSR payload 拆成 Python 字典**，别的事不归它管。

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
