"""Self-test for idraw_server: python3 test_idraw_server.py (uses the simulator, no browser)."""
import json
import os
import tempfile
import threading
import time
import urllib.request

import idraw_server

HERE = os.path.dirname(os.path.abspath(__file__))


def call(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def wait_idle(base, limit=60):
    t0 = time.time()
    while time.time() - t0 < limit:
        st = call(base + "/api/snapshot")["state"]
        if not st["busy"]:
            return st
        time.sleep(0.05)
    raise AssertionError("server stayed busy")


def main():
    tmp = tempfile.TemporaryDirectory()   # empty settings: the user's file is never touched
    idraw_server.core.SETTINGS_FILE = os.path.join(tmp.name, "settings.json")
    httpd = idraw_server.serve(os.path.join(HERE, "idraw_demo.svg"), sim=True, port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    snap = call(base + "/api/snapshot")
    assert [l["name"] for l in snap["layers"]] == ["1 Frame", "!2 Detail red", "Title block"], snap["layers"]
    assert len([s for s in snap["strokes"] if s["layer"] < 2]) == 8
    assert call(base + "/api/cmd", {"cmd": "set_title_block", "corner": "off"}) == {"ok": True}
    assert len(call(base + "/api/snapshot")["strokes"]) == 8
    assert call(base + "/api/cmd", {"cmd": "connect", "port": "Simulation"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "home"}) == {"ok": True}
    st = wait_idle(base)
    assert st["homed"] and st["origin_set"]
    assert call(base + "/api/cmd", {"cmd": "set_unit", "unit": "cm"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_paper", "w": 148, "h": 105, "name": "A6", "orient": "landscape"}) == {"ok": True}
    snap = call(base + "/api/snapshot")           # A4 drawing 1:1 on A6: paths leave the sheet
    assert snap["outside"] > 0 and any(s["out"] for s in snap["strokes"]) and snap["beyond"] == 0, (snap["outside"], snap["beyond"])
    assert call(base + "/api/cmd", {"cmd": "set_paper", "w": 297, "h": 210, "name": "A4", "orient": "landscape"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_placement", "mode": "fit"}) == {"ok": True}
    assert call(base + "/api/snapshot")["outside"] == 0
    c0 = call(base + "/api/snapshot")["content"]
    assert call(base + "/api/cmd", {"cmd": "rotate", "step": 90}) == {"ok": True}
    snap = call(base + "/api/snapshot")              # turned about its centre
    c1 = snap["content"]
    assert snap["placement"] == "custom" and snap["tf"]["rot"] == 90
    assert abs((c0[0] + c0[2]) - (c1[0] + c1[2])) < 1e-6 and abs((c1[2] - c1[0]) - (c0[3] - c0[1])) < 1e-6
    assert call(base + "/api/cmd", {"cmd": "align", "h": "left", "v": "top", "margin": 5}) == {"ok": True}
    assert [round(v, 6) for v in call(base + "/api/snapshot")["content"][:2]] == [5, 5]
    assert call(base + "/api/cmd", {"cmd": "move_by", "dx": 3, "dy": -1}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_transform", "x": 12}) == {"ok": True}
    c2 = call(base + "/api/snapshot")["content"]
    assert abs(c2[0] - 12) < 1e-6 and abs(c2[1] - 4) < 1e-6, c2
    assert "error" in call(base + "/api/cmd", {"cmd": "rotate", "step": 10})
    assert "error" in call(base + "/api/cmd", {"cmd": "set_transform", "scale": 0})
    assert call(base + "/api/cmd", {"cmd": "set_placement", "mode": "fit"}) == {"ok": True}   # preset, still turned
    snap = call(base + "/api/snapshot")
    assert snap["tf"]["rot"] == 90 and snap["outside"] == 0
    assert call(base + "/api/cmd", {"cmd": "rotate", "step": -90}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_placement", "mode": "fit"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_layer", "index": 1, "pause": False}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "jog", "dx": 10, "dy": 0}) == {"ok": True}
    assert abs(wait_idle(base)["x"] - 10) < 1e-6
    assert call(base + "/api/cmd", {"cmd": "plot"}) == {"ok": True}
    st = wait_idle(base, 120)
    snap = call(base + "/api/snapshot")
    assert snap["progress"]["i"] == 8 and snap["unit"] == "cm", snap["progress"]   # title block off
    assert st["status"] == "ready" and abs(st["x"]) < 1e-6
    assert call(base + "/api/cmd", {"cmd": "frame", "kind": "drawing"}) == {"ok": True}
    assert wait_idle(base)["status"] == "ready"
    assert call(base + "/api/cmd", {"cmd": "set_layer", "index": 1, "pause": True}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "plot", "start": 4, "end": 5}) == {"ok": True}   # first path of the ! layer
    assert wait_idle(base, 10)["status"] == "ready"                                        # no pause: does not wait
    snap = call(base + "/api/snapshot")
    assert snap["progress"]["i"] == 5 and "Plotting only path 5 of 8." in snap["log"], snap["progress"]
    assert "error" in call(base + "/api/cmd", {"cmd": "plot", "start": 8, "end": 9})
    assert "error" in call(base + "/api/cmd", {"cmd": "plot", "start": 3, "end": 3})
    assert "error" in call(base + "/api/cmd", {"cmd": "nonsense"})
    httpd.shutdown()
    print("ok")


if __name__ == "__main__":
    main()
