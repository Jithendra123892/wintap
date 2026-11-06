"""WinTap CLI.

  wintap serve                     local web GUI (monitor / calibrate / model / live)
  wintap monitor [--record F]     live tap trace in the terminal
  wintap calibrate --rows R --cols C --per-zone N
  wintap noise --seconds S         record everyday bumps as rejection examples
  wintap train                     cross-validate and pick the best model
  wintap live [--enable-actions]   run zone actions on predicted taps
  wintap status                    JSON status
  wintap demo [--fast]             full pipeline on a simulated laptop (no IMU needed)
  wintap sources                   what sensors this machine exposes
  wintap defaults                  write the default 2x2 zone actions into the config

Global: --data DIR (default %LOCALAPPDATA%\\WinTap), --source auto|winrt|hid|synthetic|replay:FILE
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path


def default_data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return str(Path(base) / "WinTap")
    return str(Path.home() / ".wintap")


def build_app(args, source=None):
    from . import sources
    from .app import App
    src = source if source is not None else sources.make_source(args.source)
    return App(args.data, source=src, dry_run_actions=getattr(args, "dry_run", False))


def fmt_event(ev):
    s = (f"[{ev['id']:>4}] peak_g={ev['peak_g']:6.2f} deg/s  peak_a={ev['peak_a']:.3f} g"
         f"  lid={ev.get('lid')}")
    if ev.get("gated"):
        return s + f"  gated:{ev['gated']}"
    if ev.get("outcome") == "recorded":
        return s + f"  recorded -> {ev['label']}"
    if "pred" in ev:
        p = ev["pred"]
        out = s + f"  pred={p['label']} conf={p['conf']}"
        if p["rejected"]:
            out += f"  REJECTED ({p['rejected']})"
        if ev.get("action"):
            out += f"  action={ev['action']}"
        return out
    return s + f"  {ev.get('outcome')}"


def run_event_loop(app, record_path=None, poll=0.1, until=None, quiet=False):
    """Print new events until `until(app)` returns True (or forever). Returns last event id."""
    rec = open(record_path, "w", encoding="utf-8") if record_path else None
    if rec:
        rec.write('{"note":"wintap recording","fields":["k","t","x","y","z"]}\n')
        def on_sample(k, t, x, y, z):
            rec.write(json.dumps({"k": k, "t": t, "x": x, "y": y, "z": z}) + "\n")
        app.sensors.on_sample = on_sample
    try:
        last = max((e["id"] for e in app.events), default=0)
        while True:
            for ev in app.events_since(last):
                last = ev["id"]
                if not quiet:
                    print(fmt_event(ev), flush=True)
            if until and until(app):
                return last
            time.sleep(poll)
    finally:
        app.sensors.on_sample = None
        if rec:
            rec.close()


def cmd_serve(args):
    from .server import serve
    app = build_app(args)
    app.start()
    httpd = serve(app, args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"WinTap running at {url}  (data in {args.data})", flush=True)
    if app.sensors.error:
        print(f"[WARN] sensor source: {app.sensors.error}", flush=True)
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_monitor(args):
    app = build_app(args)
    app.start()
    print(f"monitoring (source={app.sensors._source.kind}, found={app.sensors.found}"
          + (f", error={app.sensors.error}" if app.sensors.error else "") + ") — Ctrl+C to stop", flush=True)
    run_event_loop(app, record_path=args.record)


def cmd_calibrate(args):
    app = build_app(args)
    app.start()
    app.calibrate_start({"rows": args.rows, "cols": args.cols, "per_zone": args.per_zone, "block": args.block})
    print(f"calibrating {args.rows}x{args.cols}, {args.per_zone} taps/zone — tap the highlighted zone in the GUI/CLI", flush=True)
    def until(a):
        st = a.status()
        c = st.get("calib")
        if c:
            print(f"\r  tap zone {c['target']}  ({c['pos']+1}/{c['total']})   ", end="", flush=True)
        return st["mode"] != "calibrate"
    run_event_loop(app, until=until, quiet=True)
    print("\ncalibration done — training model...")
    rep = app.train()
    print_report(rep)


def cmd_noise(args):
    app = build_app(args)
    app.start()
    app.negatives_start({"seconds": args.seconds})
    print(f"recording {args.seconds}s of everyday bumps as noise examples...", flush=True)
    run_event_loop(app, until=lambda a: a.status()["mode"] != "negatives", quiet=False)
    print("noise examples recorded")


def cmd_train(args):
    app = build_app(args)
    rep = app.train()
    print_report(rep)


def cmd_live(args):
    app = build_app(args, )
    if args.enable_actions:
        app.set_config({"actions_enabled": True})
    app.start()
    st = app.status()
    print(f"live (model={st['model']}, actions_enabled={app.cfg['actions_enabled']}) — Ctrl+C to stop", flush=True)
    if st.get("error"):
        print(f"[WARN] {st['error']}")
    run_event_loop(app)


def cmd_status(args):
    app = build_app(args)
    app.start()
    time.sleep(0.3)
    print(json.dumps(app.status(), indent=1, default=str))


def cmd_sources(args):
    from . import sources, inputmon
    print(json.dumps(sources.list_sources(), indent=1))
    print(f"lid_open={inputmon._state.lid_open}")
    if not sources.winrt_sensor_present() and not sources.hid_sensor_present():
        print("no IMU exposed on this machine. Options:\n"
              "  - `wintap demo`            run the full pipeline on a simulated laptop\n"
              "  - `pip install wintap[hid]` + a USB IMU breakout (BMI160/BNO055) for real hardware\n"
              "  - on a 2-in-1/convertible/tablet the built-in sensor is picked up automatically")


def cmd_defaults(args):
    app = build_app(args)
    app.set_config({"actions": {"z0": "desktop_left", "z1": "desktop_right",
                                "z2": "play_pause", "z3": "privacy_guard"}})
    print("default 2x2 actions written to config: z0=desktop_left z1=desktop_right z2=play_pause z3=privacy_guard")


def print_report(rep):
    print(f"samples={rep['n']} grid={rep['grid']['rows']}x{rep['grid']['cols']} best={rep['best']}")
    for r in rep["models"]:
        acc = r["acc"].get("Full grid")
        print(f"  {r['name']:<24} full-grid acc={'-' if acc is None else round(acc, 3)}")
    if "confusion" in rep:
        print("  confusion (rows=true, cols=pred):", rep["labels"])
        for row in rep["confusion"]:
            print("   ", row)


def cmd_demo(args):
    """Full pipeline on the synthetic laptop: calibrate -> noise -> train -> live."""
    from . import model
    from .sources.synthetic import SyntheticSource
    src = SyntheticSource(fs=800, realtime=not args.fast)
    app = build_app(args, source=src)
    app._dry_run_actions = True
    app.start()
    time.sleep(1.2)  # detector warm-up (first 1 s of samples are ignored)
    src.set_bumps(False)
    app.calibrate_start({"rows": args.rows, "cols": args.cols, "per_zone": args.per_zone, "block": 2})
    print(f"calibrating {args.rows}x{args.cols} grid, {args.per_zone} taps/zone (simulated taps)...", flush=True)
    last_pos = -1
    last_change = time.monotonic()
    deadline = time.monotonic() + (180 if args.fast else 600)
    while time.monotonic() < deadline:
        st = app.status()
        if st["mode"] != "calibrate":
            break
        c = st["calib"]
        if c["pos"] != last_pos:
            last_pos = c["pos"]
            last_change = time.monotonic()
            src.request_tap(model.zone_index(c["target"]), args.rows, args.cols)
            print(f"  tap {c['pos']+1:>2}/{c['total']} -> zone {c['target']}", flush=True)
        elif time.monotonic() - last_change > (0.3 if args.fast else 1.5):
            last_change = time.monotonic()
            src.request_tap(model.zone_index(c["target"]), args.rows, args.cols)
        time.sleep(0.01)
    print("recording noise examples (simulated desk bumps)...", flush=True)
    app.negatives_start({"seconds": 2 if args.fast else 4})
    src.set_bumps(True)
    run_event_loop(app, until=lambda a: a.status()["mode"] != "negatives", quiet=True)
    src.set_bumps(False)
    rep = app.train()
    print_report(rep)
    print("live taps (actions dry-run):", flush=True)
    app.cfg["actions_enabled"] = True
    app.set_config({"actions": {"z0": "desktop_left", "z1": "desktop_right",
                                "z2": "play_pause", "z3": "privacy_guard"}})
    last = max((e["id"] for e in app.events), default=0)
    for z in range(args.rows * args.cols):
        for _ in range(2):
            src.request_tap(z, args.rows, args.cols)
            time.sleep(0.05 if args.fast else 0.9)
    time.sleep(0.3 if args.fast else 1.2)
    n_ok = n = 0
    for ev in app.events_since(last):
        if "pred" in ev:
            n += 1
            p = ev["pred"]
            print("  " + fmt_event(ev), flush=True)
    print(f"demo done: {n} live predictions (watch pred= vs the requested zone)")


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default=argparse.SUPPRESS, help="data dir (config + calibration)")
    common.add_argument("--source", default=argparse.SUPPRESS, help="auto|winrt|hid|synthetic|replay:FILE")
    p = argparse.ArgumentParser(prog="wintap", parents=[common],
                                description="Zone taps on a Windows laptop lid from the built-in IMU. "
                                            "Based on LidTap by Yemcube.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser(parents=[common], name="serve", help="local web GUI")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--open", action="store_true")
    sp.set_defaults(fn=cmd_serve)

    sp = sub.add_parser(parents=[common], name="monitor", help="live tap trace")
    sp.add_argument("--record", default=None, help="write raw samples to this JSONL file")
    sp.set_defaults(fn=cmd_monitor)

    sp = sub.add_parser(parents=[common], name="calibrate", help="record calibration taps")
    sp.add_argument("--rows", type=int, default=2)
    sp.add_argument("--cols", type=int, default=2)
    sp.add_argument("--per-zone", type=int, default=15)
    sp.add_argument("--block", type=int, default=5)
    sp.set_defaults(fn=cmd_calibrate)

    sp = sub.add_parser(parents=[common], name="noise", help="record noise examples")
    sp.add_argument("--seconds", type=int, default=30)
    sp.set_defaults(fn=cmd_noise)

    sp = sub.add_parser(parents=[common], name="train", help="cross-validate and pick the model")
    sp.set_defaults(fn=cmd_train)

    sp = sub.add_parser(parents=[common], name="live", help="run zone actions on predicted taps")
    sp.add_argument("--enable-actions", action="store_true")
    sp.set_defaults(fn=cmd_live)

    sp = sub.add_parser(parents=[common], name="status", help="JSON status")
    sp.set_defaults(fn=cmd_status)

    sp = sub.add_parser(parents=[common], name="sources", help="list sensors this machine exposes")
    sp.set_defaults(fn=cmd_sources)

    sp = sub.add_parser(parents=[common], name="defaults", help="write default 2x2 actions to config")
    sp.set_defaults(fn=cmd_defaults)

    sp = sub.add_parser(parents=[common], name="demo", help="full pipeline on a simulated laptop (no IMU needed)")
    sp.add_argument("--fast", action="store_true", help="no real-time pacing")
    sp.add_argument("--rows", type=int, default=2)
    sp.add_argument("--cols", type=int, default=2)
    sp.add_argument("--per-zone", type=int, default=6)
    sp.set_defaults(fn=cmd_demo)

    args = p.parse_args()
    if not hasattr(args, "data"):
        args.data = default_data_dir()
    if not hasattr(args, "source"):
        args.source = "auto"
    args.fn(args)


if __name__ == "__main__":
    main()
