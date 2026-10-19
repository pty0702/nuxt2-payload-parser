# 实战逆向笔记：盼之代售（pzds.com）

这份笔记记录一次真实的 Nuxt2 SSR 站点数据抓取，包含 **走了哪些弯路、哪些路是死路、最后怎么通的**。
比 README 更有价值的是这里的「死路」——省你几天时间。

---

## 一、站点画像（一句话结论）

| 项目 | 结论 |
|---|---|
| 前端 | **Nuxt2 SSR**，JS 分片托管在 `oss.pzds.com/pzdspcssr/` |
| 后端 | `api.pzds.com/api`（Express）+ **阿里云 WAF** + **WASM 签名风控** |
| 请求门槛 | `sign`（32 位 md5）+ `random` + `PZPlatform: pc`，部分接口还要 WASM 签名 |
| 直连 API | ❌ **死路**，裸 HTTP 和页面内 fetch 都被滑块拦 |
| 可用通道 | ✅ **SSR 页面内嵌的 `window.__NUXT__`** |

---

## 二、死路（别重复踩）

### 死路 1：直接请求 API

```bash
curl -X POST https://api.pzds.com/api/web-client/v2/public/goodsPublic/page \
  -H "PZPlatform: pc" -d "gameId=7&page=1"
```

返回的是一整页阿里云滑块验证 HTML（HTTP 200，但内容不是数据）。

即使加上 `acw_tc` cookie 也不行。WAF 认的是**浏览器指纹 + 重放风险评分**。

### 死路 2：在 Playwright 页面里 `fetch` 同一个 API

```python
page.evaluate("""async () => {
  const r = await fetch('https://api.pzds.com/...', {method:'POST', credentials:'include', ...});
  return await r.text();
}""")
```

**同样被拦**。但页面自己的 axios 请求是成功的——差别在 `sign` 头。

### 死路 3：以为翻页参数是 `/goodsList/16/6/2`

实测：`?page=2` / `?pageNum=2` / 路径式 `/goodsList/16/6/2` —— **SSR 层只认 `?page=N`**（而且冷门分类第 2 页会重复首页数据，程序里做了"无新增就早停"）。

真正的翻页走的是被 WAF 挡住的 API。

---

## 三、活路：SSR payload

### 3.1 长什么样

```js
window.__NUXT__=(function(a,b,c,...){return {layout:"default",data:[{...}]}}
                 (231,"xxx",{...},...))
```

647 个形参。正文里：

```js
{goodsNo:"PW2MGN2", price:f, gameId:a, gameIdName:ai, title:"...", onStandTime:"2026-10-19 08:48:20"}
```

- `goodsNo`、`title`、`onStandTime` 是**字面量**，正则能拿
- `price`、`gameId`、`gameIdName` 是**形参引用**，正则拿不到

### 3.2 为什么不建议用 node 跑

能跑（`new Function` 执行 payload），但：

- 服务器要多装 node
- payload 里有 `window` / `document` / `navigator` 引用，得造沙箱
- 线上环境多一层依赖 = 多一个故障点

本库的做法是纯 Python 静态解析，**结果与 node 执行逐字段比对完全一致**。

### 3.3 解析要点（踩过的坑）

| 坑 | 说明 |
|---|---|
| **形参列表要找对** | `function(a,b,c)` 的 `)` 之后紧跟 `{` 才是函数体 |
| **实参里有嵌套结构和字符串** | 不能 `split(',')`，必须跳过 `{}`/`[]`/引号内部 |
| **函数体后面要拿实参** | `}` 之后紧跟 `(` 才是实参列表（有的站点是 `})`，有的直接 `}(`） |
| **`return` 前缀** | 函数体通常是 `return {...}`，解析前要剥掉 |
| **`true/false/null` 不是形参** | 实参文本里出现 `true` 时，别当标识符去查表 |
| **形参套形参** | `price:f`，而 `f` 又是别的实参引用，要递归查（限深度 8 层） |
| **key 可能带引号** | `{"a":1}` 和 `{a:1}` 都要能解析 |
| **内联函数** | `fn:function(){...}` 解析不了，跳过返回 `None`，但不能让整页失败 |

---

## 四、数据字段（盼之代售）

### 列表页 `/goodsList/{gameId}/{catalogueId}`

```
data[0].goodsList[]        # 每页 10 条
  goodsNo                  # 商品编号（唯一键）
  title                    # 标题，含皮肤价值/皮肤数等文本
  subtitle                 # 例如「可二次实名」
  price                    # 售价（形参引用！）
  goodsImg                 # 封面图
  viewsNum
  createTime / onStandTime # 创建 / 上架时间
gameName                   # 游戏名
```

### 详情页 `/goodsDetails/{goodsNo}`

```
data[0].detailsData
  status                   # ON_STAND / TRADING / SOLD / FORCE_DOWN_STAND ...
  statusName               # 在售 / 交易中 / 已售出 / 强制下架 ...
  price / transactionPrice / transactionTime / payTime
  title / goodsImg / gameIdName / goodsCatalogueIdName
```

**状态码是判断"是否卖出"的唯一可靠依据**——不能靠"商品从列表里消失"，因为列表只有几页，会被新商品挤出去。

### 已知 gameId

| 游戏 | gameId |
|---|---|
| 无畏契约 | 231 |
| 穿越火线(CF) | 16 |
| 英雄联盟(LOL) | 6 |
| 王者荣耀 | 7 |
| 和平精英 | 8 |
| 三角洲行动 | 391 |

分类 `6` = 成品号。

---

## 五、各游戏标题格式（指标提取用）

```
无畏契约: Lv150，皮肤总价值19680，铂金III，总皮肤28，刀皮4枪皮24(...)
王者荣耀: 贵族8 皮肤数量213 皮肤收集度39650 荣耀典藏1 珍品传说1 ...
英雄联盟: 76皮肤 6炫彩 2臻彩 1神话/6限定/2传说/173英雄 账号等级:166
穿越火线: 【大师2】【Lv.100 高阶大元帅】VIP6 56V，7王者，2炫金，...
```

- **皮肤价值**只有无畏契约有（`皮肤总价值`），王者用 `皮肤收集度` 近似
- **英雄联盟 / 穿越火线没有价值字段** → 做"性价比筛选"时会被价值条件全部拦掉，需要额外加一条价值留空的规则兜住

---

## 六、分页与窗口

- SSR 支持 `?page=N`（同一 session 内有效）
- 冷门分类第 2 页可能重复首页 → 抓取时要"无新 goodsNo 就停"
- 列表窗口有限（默认每页 10 条），**"从列表消失" ≠ "下架"**，必须回查详情页状态

---

## 七、反爬要点

| 项 | 实测结论 |
|---|---|
| 频率 | 单 IP 每分钟 ~16 个请求稳定；超过 30 明显风险 |
| 代理 | 隧道代理（每请求换 IP）后单轮请求可翻到 40+，无异常 |
| UA | 轮换常见桌面/移动 UA 即可 |
| Cookie | 每个代理独立 Session，避免携带过期 `acw_tc` |
| 响应头 | `X-Swift-CacheTime: 0`，页面不缓存，可以直接轮询 |

---

## 八、一句话总结

> **别跟 API 死磕，去看 SSR 页面里的 `__NUXT__`。**
> 形参映射是唯一的坑，解开之后整个站点就是纯文本解析。

---

*本笔记基于 2026-10 的实际抓取，站点可能改版，结论按「可能有效的提示」看待。*
