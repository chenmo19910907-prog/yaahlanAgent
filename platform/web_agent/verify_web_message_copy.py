#!/usr/bin/env python3
"""Web Agent 消息复制纯文本提取逻辑单测（与 chat.html 行为对齐的 Python 复刻）。"""

from __future__ import annotations

import unittest
from html.parser import HTMLParser


def to_absolute_url(url: str, origin: str = "http://127.0.0.1:18766") -> str:
    target = (url or "").strip()
    if not target or target.startswith("data:") or target.startswith("blob:"):
        return target
    if target.startswith("http"):
        return target
    return origin.rstrip("/") + ("/" + target.lstrip("/") if not target.startswith("/") else target)


def format_image_plain_label(src: str, alt: str = "图片") -> str:
    label = (alt or "图片").strip() or "图片"
    url = to_absolute_url(src or "")
    if not url:
        return f"[{label}]"
    if url.startswith("data:") or url.startswith("blob:"):
        return f"[{label}]"
    return f"[{label}] {url}"


class _MsgBodyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._in_run_status = False
        self._in_msg_images = False
        self._in_msg_files = False
        self._in_file_link = False
        self._file_name = ""
        self._file_url = ""

    def _push(self, value: str) -> None:
        text = " ".join(str(value or "").split()).strip()
        if not text or (self.parts and self.parts[-1] == text):
            return
        self.parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = set((attr.get("class") or "").split())
        if tag == "div" and "run-status" in classes:
            self._in_run_status = True
        if tag == "div" and "msg-images" in classes:
            self._in_msg_images = True
        if tag == "div" and "msg-files" in classes:
            self._in_msg_files = True
        if tag == "a" and "msg-file-link" in classes:
            self._in_file_link = True
            self._file_name = ""
            self._file_url = to_absolute_url(attr.get("href") or attr.get("data-download-url") or "")
        if tag == "img" and not self._in_run_status:
            self._push(format_image_plain_label(attr.get("src") or "", attr.get("alt") or "图片"))
        if tag == "a" and self._in_msg_images and tag != "a":
            pass
        if tag == "a" and self._in_msg_images and "msg-file-link" not in classes:
            href = to_absolute_url(attr.get("href") or "")
            if href and href != "#":
                self._push(format_image_plain_label(href, "附图"))

    def handle_endtag(self, tag: str) -> None:
        if tag == "div":
            self._in_run_status = False
            self._in_msg_images = False
            self._in_msg_files = False
        if tag == "a" and self._in_file_link:
            name = self._file_name.replace("📎", "").strip() or "附件"
            suffix = f" {self._file_url}" if self._file_url and self._file_url != "#" else ""
            self._push(f"[附件] {name}{suffix}")
            self._in_file_link = False
            self._file_name = ""
            self._file_url = ""

    def handle_data(self, data: str) -> None:
        if self._in_run_status:
            return
        if self._in_file_link:
            self._file_name += data
            return
        text = " ".join(data.replace("\xa0", " ").split()).strip()
        if text:
            self._push(text)


def extract_message_plain_text(fragment: str) -> str:
    parser = _MsgBodyParser()
    parser.feed(fragment)
    return "\n\n".join(parser.parts).strip()


class VerifyWebMessageCopy(unittest.TestCase):
    def test_image_only_message(self) -> None:
        html = (
            '<div class="msg-body"><div class="msg-images">'
            '<a href="/api/uploads/x.png"><img src="/api/uploads/x.png" alt="附图" /></a>'
            "</div></div>"
        )
        plain = extract_message_plain_text(html)
        self.assertIn("[附图]", plain)
        self.assertIn("/api/uploads/x.png", plain)

    def test_image_with_text(self) -> None:
        html = (
            '<div class="msg-body"><div class="msg-images">'
            '<img src="/api/uploads/x.png" alt="附图" />'
            "</div>测试文字</div>"
        )
        plain = extract_message_plain_text(html)
        self.assertIn("测试文字", plain)
        self.assertIn("[附图]", plain)

    def test_data_url_plain_text_is_short(self) -> None:
        data_url = "data:image/png;base64," + ("A" * 128)
        html = f'<div class="msg-body"><div class="msg-images"><img src="{data_url}" alt="附图" /></div></div>'
        plain = extract_message_plain_text(html)
        self.assertEqual(plain, "[附图]")


if __name__ == "__main__":
    unittest.main()
