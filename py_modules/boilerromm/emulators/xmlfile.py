"""Changing some elements of an emulator's XML config and leaving the rest as the emulator or the user wrote them.

Its own small reader: the Python that Decky Loader ships has no `xml` package. It covers what a settings file is made
of (nested elements, attributes, text); anything else in the file makes it unreadable, and it is then started anew.
"""
import os
import re
import tempfile
from dataclasses import dataclass, field

_TOKEN = re.compile(r"<\?.*?\?>|<!--.*?-->|<!\[CDATA\[(?P<cdata>.*?)\]\]>|<(?P<close>/)?(?P<name>[^\s<>/!?]+)(?P<attrs>[^<>]*?)(?P<empty>/)?>|(?P<text>[^<]+)", re.S)
_ENTITIES = {"&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'", "&amp;": "&"}


@dataclass
class Node:
    name: str
    attrs: str = ""
    text: str = ""
    children: list["Node"] = field(default_factory=list)

    def find(self, path: str) -> "Node | None":
        node = self
        for name in path.split("/"):
            node = next((c for c in node.children if c.name == name), None)
            if node is None:
                return None
        return node


def _unescape(text: str) -> str:
    return re.sub(r"&(?:lt|gt|quot|apos|amp);", lambda m: _ENTITIES[m.group()], text)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parse(source: str) -> Node:
    """The root element; ValueError for anything that is not one well-formed tree."""
    top = Node("")
    stack = [top]
    at = 0
    for m in _TOKEN.finditer(source):
        if m.start() != at:
            raise ValueError("not XML")
        at = m.end()
        if m["cdata"] is not None:
            stack[-1].text += m["cdata"]
        elif m["text"] is not None:
            if m["text"].strip():
                stack[-1].text += _unescape(m["text"].strip())
        elif m["name"] is None:
            continue
        elif m["close"]:
            if len(stack) < 2 or stack[-1].name != m["name"]:
                raise ValueError("not XML")
            stack.pop()
        else:
            node = Node(m["name"], m["attrs"].strip())
            stack[-1].children.append(node)
            if not m["empty"]:
                stack.append(node)
    if at != len(source) or len(stack) != 1 or len(top.children) != 1 or top.text:
        raise ValueError("not XML")
    return top.children[0]


def dump(node: Node, depth: int = 0) -> str:
    pad = "    " * depth
    head = f"{pad}<{node.name}{' ' + node.attrs if node.attrs else ''}"
    if node.children:
        inner = "".join(dump(c, depth + 1) for c in node.children)
        return f"{head}>\n{inner}{pad}</{node.name}>\n"
    return f"{head}>{_escape(node.text)}</{node.name}>\n" if node.text else f"{head}/>\n"


def _load(path: str) -> Node | None:
    try:
        with open(path, encoding="utf-8") as f:
            return parse(f.read())
    except (OSError, ValueError):
        return None


def _element(root: Node, path: str) -> tuple[Node, bool]:
    node, created = root, False
    for name in path.split("/"):
        child = node.find(name)
        if child is None:
            child, created = Node(name), True
            node.children.append(child)
        node = child
    return node, created


def update(path: str, root_name: str, values: dict[str, str] | None = None, defaults: dict[str, str] | None = None) -> None:
    """`values` are always written; `defaults` only where the element is not there yet. Keys are "/"-separated element paths."""
    root = _load(path) or Node(root_name)
    for items, overwrite in ((defaults, False), (values, True)):
        for key, value in (items or {}).items():
            node, created = _element(root, key)
            if overwrite or created:
                node.text = value
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=f".{os.path.basename(path)}-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n' + dump(root))
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read(path: str, key: str, fallback: str = "") -> str:
    root = _load(path)
    node = root.find(key) if root else None
    return fallback if node is None else node.text
