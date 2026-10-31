#!/usr/bin/env python3
"""自动生成个人主页 README 的「📡 仓库动态」区块。

由 .github/workflows/update-dynamics.yml 每日定时调用，也可本地直接运行：
    python3 .github/scripts/update_dynamics.py

只重写 DYNAMIC:START / DYNAMIC:END 标记之间的内容；
首次运行若标记不存在，则把整个区块插入到 GitHub Stats 区块之前。

内容来源（gh api，公开数据即可）：
- 自有仓库（排除 fork 与主页仓库本身），按最近推送排序
- 各仓库最新 Release，按发布时间排序
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

USER = "huluohu"
README_PATH = "README.md"
START_MARK = "<!-- 🤖 DYNAMIC:START -->"
END_MARK = "<!-- 🤖 DYNAMIC:END -->"
INSERT_ANCHOR = "<!-- ═══════════════ GITHUB STATS ═══════════════ -->"
TZ = timezone(timedelta(hours=8))  # 以北京时间展示
NEW_REPO_DAYS = 30  # 创建不足 30 天的仓库标记 🆕
ACTIVE_LIMIT = 6  # 活跃项目展示条数
RELEASE_LIMIT = 5  # 最新发布展示条数


def gh(path: str):
    """通过 gh CLI 调 GitHub API，失败即退出。"""
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"gh api {path} 失败: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def gh_optional(path: str):
    """同上，但 404 等错误返回 None（比如仓库还没有任何 Release）。"""
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def parse_time(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def relative_date(iso: str, now: datetime) -> str:
    days = (now - parse_time(iso)).days
    if days <= 0:
        return "今天"
    if days == 1:
        return "昨天"
    if days < 30:
        return f"{days} 天前"
    return iso[:10]


def one_line(text: str, limit: int = 80) -> str:
    line = (text or "（暂无描述）").strip().split("\n")[0]
    return line if len(line) <= limit else line[: limit - 1] + "…"


def build_section(now_utc: datetime) -> str:
    now = now_utc.astimezone(TZ)
    repos = gh(f"users/{USER}/repos?per_page=100")
    own = [
        r
        for r in repos
        if not r["fork"]
        and r["name"] != USER
        and not r["archived"]  # GitHub 上已归档的仓库
        and not r["name"].lower().endswith("-archive")  # 历史快照仓库（如 HawkSnap-0.3.0-archive）
    ]
    own.sort(key=lambda r: r["pushed_at"], reverse=True)
    active_cutoff = now_utc - timedelta(days=90)  # 90 天内推过代码才算「活跃」
    active = [r for r in own if parse_time(r["pushed_at"]) >= active_cutoff]

    lines = [
        "## 📡 仓库动态",
        "",
        f"> 🤖 本区块由 GitHub Actions 每日自动更新 · 最后更新 {now.strftime('%Y-%m-%d %H:%M')} (UTC+8)",
        "",
        "### 🔨 活跃项目",
        "",
    ]

    for r in active[:ACTIVE_LIMIT]:
        is_new = (now_utc - parse_time(r["created_at"])) < timedelta(days=NEW_REPO_DAYS)
        badge = "🆕 " if is_new else ""
        lang = f" · `{r['language']}`" if r["language"] else ""
        stars = f" · ⭐ {r['stargazers_count']}" if r["stargazers_count"] else ""
        desc = one_line(r["description"])
        pushed = relative_date(r["pushed_at"], now)
        lines.append(
            f"- {badge}**[{r['name']}]({r['html_url']})**{lang}{stars} — {desc}（更新于 {pushed}）"
        )

    # 各仓库最新 Release（忽略草稿），按发布时间倒序
    releases = []
    for r in own:
        rels = gh_optional(f"repos/{USER}/{r['name']}/releases?per_page=10") or []
        rels = [x for x in rels if not x.get("draft")]
        if rels:
            releases.append(rels[0])
    releases.sort(
        key=lambda x: x.get("published_at") or x["created_at"], reverse=True
    )

    if releases[:RELEASE_LIMIT]:
        lines += ["", "### 🚀 最新发布", ""]
        for rel in releases[:RELEASE_LIMIT]:
            name = rel["name"] or rel["tag_name"]
            repo_name = rel["html_url"].split("/releases/")[0].rsplit("/", 1)[-1]
            pre = " 🧪" if rel.get("prerelease") else ""
            when = relative_date(rel.get("published_at") or rel["created_at"], now)
            lines.append(f"- **[{repo_name} · {name}]({rel['html_url']})**{pre} — {when}")

    return "\n".join(lines)


def main() -> None:
    now_utc = datetime.now(timezone.utc)
    block = START_MARK + "\n" + build_section(now_utc) + "\n" + END_MARK

    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()

    if START_MARK in content and END_MARK in content:
        before, rest = content.split(START_MARK, 1)
        _, after = rest.split(END_MARK, 1)
        new_content = before + block + after
    elif INSERT_ANCHOR in content:
        new_content = content.replace(
            INSERT_ANCHOR, block + "\n\n---\n\n" + INSERT_ANCHOR, 1
        )
    else:
        sys.exit("README 中找不到动态区块标记，也没有可插入的锚点")

    if new_content == content:
        print("README 已是最新，无需修改")
        return

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("README 仓库动态区块已更新")


if __name__ == "__main__":
    main()
