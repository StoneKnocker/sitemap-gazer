# sitemap-gazer

[README 英文版](README.md)

一个帮你轻易监控网站变更的工具。

它爬取 sitemap，记住见过的每个 URL，并把新增 URL 写进 data/README.md。每次运行都会重写这份报告：开头是本次新发现的 URL，后面才是各站最近的历史记录。一份报告可以同时监控多个站点。抓取失败、返回 0 页，或页数明显少于上次有效抓取时，这次结果会被丢掉。一个站点失败不会挡住其他站点。

它也可以直接在 Github Action 运行，示例： [hackerqed/sitemap-gazer-example](https://github.com/hackerqed/sitemap-gazer-example)

## 安装

```bash
pip install sitemap-gazer

mkdir sitemap-gazer-report
cd sitemap-gazer-report

sitemap-gazer init
# 创建 sitemap-gazer.json

# 编辑 sitemap-gazer.json
# 例如增加一个目标站点 crazygames.com
# {
#   "sites": [
#     {
#       "name": "crazygames.com",
#       "url": "https://crazygames.com/",
#       "sitemap_url": "https://crazygames.com/sitemap.xml",
#       "include": [],
#       "exclude": [],
#       "strip_locales": false,
#       "group_suffixes": []
#     }
#   ],
#   "genReadme": true,
#   "output_dir": "data",
#   "readme_limit": 10,
#   "min_page_ratio": 0.8
# }

sitemap-gazer
# 爬取数据，保存到 ./data/<site>/
# 新增 URL 写到 ./data/README.md，不改项目根目录的 README.md
```

## 开发

运行开发版：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
sitemap-gazer
```

打包并安装：

```bash
pip install build
python -m build
pip install dist/sitemap_gazer-0.0.4-py3-none-any.whl
```
