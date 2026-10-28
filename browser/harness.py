"""Runs inside every browser_exec call, before Morzik's code (the morzik-browser plugin adds the line).

Morzik's Chrome is his screen, and the user sees it in the Morzik App: the tab he works in must be the one in
front. browser_harness attaches to tabs without showing them (switch_tab(activate=False), new_tab in the
background), and a background tab is not painted: screenshots time out and clicks miss. So here switch_tab
shows the tab by default, the current tab comes to the front now and once more when the call ends, and then
old tabs beyond KEEP are closed (least recently worked in first).

Globals from the plugin: G (browser_harness.run's globals, where Morzik's code runs), STATE (json file with
the tabs' last use), KEEP.
"""

import atexit
import json
import os
import time

import browser_harness.helpers as h

_plain, _traced = h.switch_tab, G.get("switch_tab", h.switch_tab)


def _switch(target, activate=True):
    return _plain(target, activate)


def _switch_traced(target, activate=True):
    return _traced(target, activate=activate)


_switch.__doc__ = _switch_traced.__doc__ = "Attach the agent to a tab and show it on the screen."
h.switch_tab, G["switch_tab"] = _switch, _switch_traced


def _front():
    """The tab Morzik works in, brought to the front; None when there is no usable one."""
    try:
        tab = h.current_tab()
        h.activate_tab(tab)
        return tab
    except Exception:
        return None


def _load():
    try:
        with open(STATE) as f:
            used = json.load(f).get("used", {})
        return used if isinstance(used, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _save(current, used):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"current": current, "used": used, "at": time.time()}, f)
    os.replace(tmp, STATE)


def _tidy(current):
    now = time.time()
    tabs = [t["targetId"] for t in h.list_tabs()]
    old = _load()
    # A tab seen for the first time counts as just used: it may be a page this call opened.
    used = {tid: float(old.get(tid, now)) for tid in tabs}
    if current:
        used[current] = now
    for tid in sorted((t for t in tabs if t != current), key=used.get)[:max(0, len(tabs) - KEEP)]:
        try:
            h.close_tab(tid)
            used.pop(tid, None)
        except Exception:
            pass
    _save(current, used)


def _finish():
    tab = _front()
    try:
        _tidy(tab["targetId"] if tab else None)
    except Exception:
        pass


_front()
atexit.register(_finish)
