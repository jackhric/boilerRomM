"""The frontend and the backend name the same calls, events and state: both sides are written by hand."""
import ast
import logging
import os
import re

from boilerromm import app as app_module
from boilerromm.app import App

ROOT = os.path.join(os.path.dirname(__file__), "..")
API = open(os.path.join(ROOT, "src", "api.ts"), encoding="utf-8").read()
LIFECYCLE = {"_main", "_unload", "_uninstall", "_migration"}


async def _noop(*a):
    pass


def test_every_call_the_frontend_makes_exists_and_nothing_else_is_exposed():
    called = set(re.findall(r'callable<.*>\("(\w+)"\)', API))
    tree = ast.parse(open(os.path.join(ROOT, "main.py"), encoding="utf-8").read())
    plugin = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    exposed = {n.name for n in plugin.body if isinstance(n, ast.AsyncFunctionDef)} - LIFECYCLE
    assert called - exposed == set(), "the frontend calls methods the backend does not have"
    assert exposed - called == set(), "the backend exposes methods nothing calls"


def test_event_names_match():
    names = dict(re.findall(r'const (\w+_EVENT) = "(\w+)";', API))
    assert names == {"STATE_EVENT": app_module.STATE_EVENT, "PROGRESS_EVENT": app_module.PROGRESS_EVENT}


def test_the_state_has_exactly_the_keys_the_frontend_declares(tmp_path):
    body = re.search(r"export interface State \{(.*?)\n\}", API, re.S).group(1)
    declared = set(re.findall(r"^  (\w+)\??:", body, re.M))
    state = App(str(tmp_path / "settings.json"), "1", str(tmp_path), _noop, logging.getLogger("t")).state()
    assert set(state) == declared


def test_the_frontend_opens_the_same_sign_in_page_the_backend_follows():
    from boilerromm.signin import OPENID_URL

    declared = re.search(r"export const SGDB_SIGN_IN =(.*?);", API, re.S).group(1)
    assert "".join(re.findall(r'"([^"]*)"', declared)) == OPENID_URL
