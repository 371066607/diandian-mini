# 众包关键词语料库 · Cloudflare Worker + D1

全体客户端共享的关键词池。客户端扫描覆盖词时，把发现的关键词（**仅关键词 + 地区 +
来源 + 是否命中**，不含 app_id / 用户标识）上报到这里，并从这里回流候选词 —— 用得越多，
所有人的候选池越大。

## 部署（约 15 分钟，需一个 Cloudflare 免费账号）

```bash
cd server/corpus-worker
npm install                     # 装本地锁定版 wrangler（package.json 已固定版本）

# 之后全程用 npx 调用 wrangler（会用上面装的本地版，版本可复现；也免去全局安装+配 PATH 的坑）
npx wrangler login              # 浏览器授权（需 Cloudflare 免费账号）
npx wrangler whoami             # 可选：确认已登录

# 1) 建 D1 数据库，把输出的 database_id 填进 wrangler.jsonc
npx wrangler d1 create diandian-corpus

# 2) 建表（远程库）
npx wrangler d1 execute diandian-corpus --remote --file=schema.sql

# 3) 设置共享密钥（随机串），同一个值要填进客户端
npx wrangler secret put API_KEY     # 粘贴一串随机字符，回车

# 4) 部署（可先 --dry-run 校验），记下打印出的 https://diandian-corpus.<子域>.workers.dev
npx wrangler deploy --dry-run   # 可选：只校验不真正部署
npx wrangler deploy
```

部署后把 **Worker URL** 和 **API_KEY** 告诉我（或自己填），写进客户端：
`app/services/keyword_corpus_service.py` 顶部的 `CORPUS_API_URL` / `CORPUS_API_KEY`。
填好提交后，老用户通过热更新即可接入共享库；为空时客户端自动退回纯本地模式。

## 建议（生产）
- Cloudflare 控制台给该 Worker 加一条 **Rate Limiting** 规则（按 IP 限速），防刷。
- D1 免费额度：5GB 存储、5M 行读/日、10万行写/日 —— 对本用途绰绰有余。

## 接口
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/contribute` | `{platform,country,lang,items:[{keyword,source,confirmed}]}` 批量沉淀（≤500 条/次） |
| GET | `/candidates?platform=&country=&lang=&tokens=a,b,c&limit=80` | 返回与 tokens 有词重叠的候选词，confirmed/高频优先 |
| GET | `/stats?platform=&country=&lang=` | 该地区已收录关键词数 |

所有请求需带头 `x-api-key:<API_KEY>`（当 secret 已设置时）。

## 本地调试
```bash
echo 'API_KEY=local-dev-key' > .dev.vars   # 本地密钥（已 gitignore，勿提交）
npx wrangler d1 execute diandian-corpus --local --file=schema.sql   # 本地库建表
npx wrangler dev                            # 本地起 Worker（默认本地 D1）
```
