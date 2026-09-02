"""Self-test for idraw_server: python3 test_idraw_server.py (uses the simulator, no browser)."""
import json
import os
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
    httpd = idraw_server.serve(os.path.join(HERE, "idraw_demo.svg"), sim=True, port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    snap = call(base + "/api/snapshot")
    assert [l["name"] for l in snap["layers"]] == ["1 Frame", "!2 Detail red"], snap["layers"]
    assert len(snap["strokes"]) == 8
    assert call(base + "/api/cmd", {"cmd": "connect", "port": "Simulation"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "home"}) == {"ok": True}
    st = wait_idle(base)
    assert st["homed"] and st["origin_set"]
    assert call(base + "/api/cmd", {"cmd": "set_unit", "unit": "cm"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_placement", "mode": "fit"}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "set_layer", "index": 1, "pause": False}) == {"ok": True}
    assert call(base + "/api/cmd", {"cmd": "jog", "dx": 10, "dy": 0}) == {"ok": True}
    assert abs(wait_idle(base)["x"] - 10) < 1e-6
    assert call(base + "/api/cmd", {"cmd": "plot"}) == {"ok": True}
    st = wait_idle(base, 120)
    snap = call(base + "/api/snapshot")
    assert snap["progress"]["i"] == 8 and snap["unit"] == "cm", snap["progress"]
    assert st["status"] == "ready" and abs(st["x"]) < 1e-6
    assert "error" in call(base + "/api/cmd", {"cmd": "nonsense"})
    httpd.shutdown()
    print("ok")


if __name__ == "__main__":
    main()
