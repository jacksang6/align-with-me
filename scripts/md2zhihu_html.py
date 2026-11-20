"""Convert launch-post-zh.md to HTML for zhihu's rich-text editor paste.

Hand-rolled for this document's known structures: blockquote, ##/### headings,
bold, bullet lists, links, a table, one image line (dropped - uploaded separately),
code fence, hr, inline code.
"""
import html as html_mod
import json
import re
import sys

SRC = r"C:\Users\lenovo\repos\align-with-me\docs\launch-post-zh.md"
OUT = r"C:\Users\lenovo\AppData\Local\Temp\zhihu-article.json"


def inline(s: str) -> str:
    s = html_mod.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    # links [text](url)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" rel="noopener">\1</a>', s)
    return s


def main():
    lines = open(SRC, encoding="utf-8").read().split("\n")
    out: list[str] = []
    i = 0
    in_table = False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("!["):          # image line: skipped, uploaded manually
            i += 1
            continue
        if stripped.startswith("---") and len(stripped) <= 5:
            out.append("<hr/>")
            i += 1
            continue
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(html_mod.escape(lines[i]))
                i += 1
            i += 1
            out.append("<pre>" + "\n".join(buf) + "</pre>")
            continue
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.fullmatch(r"-{2,}:?|:-+:?", c) for c in cells):  # separator row
                i += 1
                continue
            if not in_table:
                out.append("<table><tbody>")
                in_table = True
            row = "".join(f"<td>{inline(c)}</td>" for c in cells)
            out.append(f"<tr>{row}</tr>")
            i += 1
            continue
        if in_table:
            out.append("</tbody></table>")
            in_table = False
        if stripped.startswith("### "):
            out.append(f"<h3>{inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            out.append(f"<h2>{inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            pass  # title lives in the title field
        elif stripped.startswith("> "):
            out.append(f"<blockquote><p>{inline(stripped[2:])}</p></blockquote>")
        elif stripped == ">":
            out.append("<blockquote><p><br/></p></blockquote>")
        elif stripped.startswith("- "):
            out.append(f"<ul><li>{inline(stripped[2:])}</li></ul>")
        elif re.match(r"^\d+\.\s", stripped):
            out.append(f"<ol><li>{inline(re.sub(r'^\\d+\\.\\s', '', stripped))}</li></ol>")
        elif stripped == "":
            pass
        else:
            out.append(f"<p>{inline(stripped)}</p>")
        i += 1
    if in_table:
        out.append("</tbody></table>")
    html = "".join(out)
    json.dump({"html": html}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[OK] {len(html)} chars -> {OUT}")


if __name__ == "__main__":
    main()
