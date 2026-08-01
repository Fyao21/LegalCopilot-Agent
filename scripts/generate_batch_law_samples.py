import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_import import parse_knowledge_text_file  # noqa: E402

ARTICLE_HEADING = re.compile(r"(?m)^[ \t\u3000]*(第[一二三四五六七八九十百零〇两]+条)(?=[ \t\u3000])")
SPACE_RUN = re.compile(r"[ \t\u3000]+")
TRAILING_HEADING = re.compile(r"^第[一二三四五六七八九十百零〇两]+[章节编](?:\s+.*)?$")


@dataclass(frozen=True)
class LawSource:
    slug: str
    law_name: str
    domain: str
    url: str
    article_count: int = 20


SOURCES = [
    LawSource(
        "labor_contract",
        "中华人民共和国劳动合同法",
        "劳动用工",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_0abfdd261c03417b949df19d869add8d.html",
    ),
    LawSource(
        "consumer_rights",
        "中华人民共和国消费者权益保护法",
        "消费者权益",
        "https://www.samr.gov.cn/zt/ndzt/2019n/bjspjsqjxcjwljxyjsckpxc/zcfg/"
        "art/2023/art_5004b2b0f4154c76acfca499fe9c737a.html",
    ),
    LawSource(
        "circular_economy",
        "中华人民共和国循环经济促进法",
        "资源与环境",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_1ad5f68735884d669bc61d75625e3764.html",
    ),
    LawSource(
        "advertising",
        "中华人民共和国广告法",
        "广告合规",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_5474cf75173c45d6a0379730fb4e8d97.html",
    ),
    LawSource(
        "antimonopoly",
        "中华人民共和国反垄断法",
        "公平竞争",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_f0fae9eb3a684fc39e84d89eabfc2caa.html",
    ),
    LawSource(
        "price",
        "中华人民共和国价格法",
        "价格监管",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/jls/art/2023/art_3da9131ab041449d9af2af886ee33766.html",
    ),
    LawSource(
        "metrology",
        "中华人民共和国计量法",
        "计量监管",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_53e03a5515914e73a65e2f370907271e.html",
    ),
    LawSource(
        "drug_administration",
        "中华人民共和国药品管理法",
        "药品监管",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_b73ec9dabb2d468281d6c994b4bcdaf8.html",
    ),
    LawSource(
        "ecommerce",
        "中华人民共和国电子商务法",
        "电子商务",
        "https://www.samr.gov.cn/zfjcj/tzgg/art/2023/art_d337c3291e8b40459ca03dea54395856.html",
    ),
    LawSource(
        "food_safety",
        "中华人民共和国食品安全法",
        "食品安全",
        "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_6bff4ef87291497fa72949e1fc88efb5.html",
    ),
]


class VisibleTextParser(HTMLParser):
    BLOCK_TAGS = {"article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section", "tr"}
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        elif not self.skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts)).replace("\xa0", " ")
        lines = [SPACE_RUN.sub(" ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def chinese_article_number(number: int) -> str:
    digits = "零一二三四五六七八九"
    if number < 10:
        value = digits[number]
    elif number == 10:
        value = "十"
    elif number < 20:
        value = f"十{digits[number - 10]}"
    elif number % 10 == 0:
        value = f"{digits[number // 10]}十"
    else:
        value = f"{digits[number // 10]}十{digits[number % 10]}"
    return f"第{value}条"


def extract_articles(page_html: str) -> dict[str, str]:
    parser = VisibleTextParser()
    parser.feed(page_html)
    text = parser.text()
    matches = list(ARTICLE_HEADING.finditer(text))
    candidates: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content_lines = text[match.end() : end].strip().splitlines()
        while content_lines and TRAILING_HEADING.fullmatch(content_lines[-1].strip()):
            content_lines.pop()
        content = "\n".join(content_lines).strip()
        article_number = match.group(1)
        if len(content) > len(candidates.get(article_number, "")):
            candidates[article_number] = content
    return candidates


def fetch_source(client: httpx.Client, source: LawSource) -> dict[str, str]:
    response = client.get(source.url)
    response.raise_for_status()
    articles = extract_articles(response.text)
    missing = [
        chinese_article_number(number)
        for number in range(1, source.article_count + 1)
        if chinese_article_number(number) not in articles
    ]
    if missing:
        raise RuntimeError(f"{source.law_name} 缺少条文：{', '.join(missing)}")
    return articles


def generate(output_dir: Path) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    sequence = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138 Safari/537.36"
        )
    }
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for source in SOURCES:
            articles = fetch_source(client, source)
            generated_files: list[str] = []
            for number in range(1, source.article_count + 1):
                sequence += 1
                article_number = chinese_article_number(number)
                content = articles[article_number]
                filename = f"{sequence:03d}_{source.slug}_{number:03d}.txt"
                path = output_dir / filename
                text = "\n".join([source.law_name, article_number, source.url, content]) + "\n"
                path.write_text(text, encoding="utf-8")
                parse_knowledge_text_file(filename, path.read_bytes())
                generated_files.append(filename)
            manifest.append(
                {
                    **asdict(source),
                    "generated_files": generated_files,
                }
            )
    if sequence != 200:
        raise RuntimeError(f"预期生成 200 个文件，实际为 {sequence}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="从可核验官方页面生成四行格式的批量法规 TXT")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("examples/batch_laws"),
        help="TXT 输出目录",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("examples/batch_laws_manifest.json"),
        help="来源清单输出文件",
    )
    args = parser.parse_args()
    manifest = generate(args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "generated_on": date.today().isoformat(),
                "format": ["法律名称", "条号", "来源", "正文（第四行起）"],
                "total_files": sum(len(item["generated_files"]) for item in manifest),
                "notice": "公开法规教学数据；导入和正式使用前仍需核对效力状态与权威原文。",
                "sources": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"generated=200 output={args.output} manifest={args.manifest}")


if __name__ == "__main__":
    main()
