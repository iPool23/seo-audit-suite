# SEO MCP

一个基于 Ahrefs 数据的 MCP（Model Control Protocol）SEO 工具服务。包含反向链接分析、关键词研究、流量估算等功能。

[English](./README.md)

## 概述

该服务提供了从 Ahrefs 获取 SEO 数据的 API。它处理整个过程，包括验证码解决、认证和数据检索。结果会被缓存以提高性能并减少 API 成本。

如果你只想对一个公开网站做基础页面 SEO 检查，而不想依赖 Ahrefs 或 CapSolver，可以直接使用项目内置的 `seo_audit` 工具。它默认会抓取少量站内页面。

> 此 MCP 服务仅供学习使用，请勿滥用。本项目受 `@哥飞社群` 启发。

## 功能特性

- 🔍 反向链接分析
  - 获取任意域名的详细反向链接数据
  - 查看域名评分、锚文本和链接属性
  - 筛选教育和政府域名
- 🎯 关键词研究
  - 从种子关键词生成关键词创意
  - 获取关键词难度评分
  - 查看搜索量和趋势
- 📊 流量分析

  - 估算网站流量
  - 查看流量历史和趋势
  - 分析热门页面和国家分布
  - 跟踪关键词排名

- 🌐 公共页面 SEO 审计

  - 无需 CapSolver 即可抓取公开网站的少量站内页面
  - 检查 title、meta description、标题层级、canonical、图片、链接、可索引性和页面评分

- 🧾 SEO 报告导出

  - 从抓取结果生成可分享的 HTML 或 Markdown 报告
  - 一眼看到评分分布、常见问题、最差页面和下一步建议

- 🚀 性能优化
  - 使用 CapSolver 自动解决验证码
  - 响应缓存

## 安装

### 前置要求

- Python 3.10 或更高版本
- 只有在使用 Ahrefs 相关工具时才需要 CapSolver 账号和 API 密钥（[点此注册](https://dashboard.capsolver.com/passport/register?inviteCode=1dTH7WQSfHD0)）

### 从 PyPI 安装

```bash
pip install seo-mcp
```

或使用 `uv`：

```bash
uv pip install seo-mcp
```

### 手动安装

1. 克隆仓库：

   ```bash
   git clone https://github.com/cnych/seo-mcp.git
   cd seo-mcp
   ```

2. 安装依赖：

   ```bash
   pip install -e .
   # 或
   uv pip install -e .
   ```

3. 设置 CapSolver API 密钥：
   ```bash
   export CAPSOLVER_API_KEY="your-capsolver-api-key"
   ```

  如果你只使用公共 SEO 审计工具，可以跳过这一步。

## 使用方法

### 运行服务

您可以通过以下方式运行服务：

#### 在 Cursor IDE 中使用

在 Cursor 设置中，切换到 MCP 标签页，点击 `+Add new global MCP server` 按钮，然后输入：

```json
{
  "mcpServers": {
    "SEO MCP": {
      "command": "uvx",
      "args": ["--python", "3.10", "seo-mcp"],
      "env": {
        "CAPSOLVER_API_KEY": "CAP-xxxxxx"
      }
    }
  }
}
```

您也可以在项目根目录创建 `.cursor/mcp.json` 文件，内容同上。

### 导出报告

从公开网站生成可视化 HTML 报告或 Markdown 摘要：

```bash
seo-report ucv.edu.pe --format html --max-pages 4
```

默认会把报告保存到 `reports/` 目录。可以用 `--output` 指定文件名，或者用 `--format markdown` 导出 Markdown 版本。

### API 参考

该服务提供以下 MCP 工具：

#### `get_backlinks_list(domain: str)`

获取域名的反向链接。

**参数：**

- `domain`（字符串）：要分析的域名（例如："example.com"）

**返回：**

```json
{
  "overview": {
    "domainRating": 76,
    "backlinks": 1500,
    "refDomains": 300
  },
  "backlinks": [
    {
      "anchor": "示例链接",
      "domainRating": 76,
      "title": "页面标题",
      "urlFrom": "https://referringsite.com/page",
      "urlTo": "https://example.com/page",
      "edu": false,
      "gov": false
    }
  ]
}
```

#### `keyword_generator(keyword: str, country: str = "us", search_engine: str = "Google")`

生成关键词创意。

**参数：**

- `keyword`（字符串）：种子关键词
- `country`（字符串）：国家代码（默认："us"）
- `search_engine`（字符串）：搜索引擎（默认："Google"）

**返回：**

```json
[
  {
    "keyword": "示例关键词",
    "volume": 1000,
    "difficulty": 45,
    "cpc": 2.5
  }
]
```

#### `get_traffic(domain_or_url: str, country: str = "None", mode: str = "subdomains")`

获取流量估算。

**参数：**

- `domain_or_url`（字符串）：要分析的域名或 URL
- `country`（字符串）：国家筛选（默认："None"）
- `mode`（字符串）：分析模式（"subdomains" 或 "exact"）

**返回：**

```json
{
  "traffic_history": [...],
  "traffic": {
    "trafficMonthlyAvg": 50000,
    "costMontlyAvg": 25000
  },
  "top_pages": [...],
  "top_countries": [...],
  "top_keywords": [...]
}
```

#### `keyword_difficulty(keyword: str, country: str = "us")`

获取关键词难度评分。

**参数：**

- `keyword`（字符串）：要分析的关键词
- `country`（字符串）：国家代码（默认："us"）

**返回：**

```json
{
  "difficulty": 45,
  "serp": [...],
  "related": [...]
}
```

#### `seo_audit(url_or_domain: str, max_pages: int = 5, timeout: int = 20)`

对一个公开网站进行基础页面 SEO 检查，并抓取少量站内页面。

**参数：**

- `url_or_domain`（字符串）：要分析的完整 URL 或域名，例如 `https://ucv.edu.pe` 或 `ucv.edu.pe`
- `max_pages`（整数）：最多抓取的站内页面数，默认 5
- `timeout`（整数）：请求超时时间，单位秒

**返回：**

```json
{
  "start_url": "https://www.ucv.edu.pe/",
  "max_pages": 5,
  "pages": [
    {
      "final_url": "https://www.ucv.edu.pe/",
      "score": 85,
      "title": "UCV | Universidad César Vallejo"
    }
  ],
  "aggregate": {
    "page_count": 5,
    "average_score": 88.8,
    "common_issues": []
  }
}
```

## 开发

对于开发：

```bash
git clone https://github.com/cnych/seo-mcp.git
cd seo-mcp
uv sync
```

## 工作原理

1. 用户通过 MCP 发送请求
2. 服务使用 CapSolver 解决 Cloudflare Turnstile 验证码
3. 从 Ahrefs 获取认证令牌
4. 检索请求的 SEO 数据
5. 处理并返回格式化结果

## 故障排除

- **CapSolver API 密钥错误**：检查 `CAPSOLVER_API_KEY` 环境变量
- **速率限制**：减少请求频率
- **无结果**：域名可能未被 Ahrefs 收录
- **其他问题**：查看 [GitHub 仓库](https://github.com/cnych/seo-mcp)

## 许可证

MIT 许可证 - 详见 LICENSE 文件
