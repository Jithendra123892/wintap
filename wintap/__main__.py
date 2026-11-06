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
  wintap features [options]        manage feature toggles (--list, --enable, --disable, --reset, --status)
  wintap quickstart [options]      interactive setup wizard (--rows, --cols, --per-zone)
  wintap version                   show version

Global: --data DIR (default %LOCALAPPDATA%\\WinTap), --source auto|winrt|hid|audio|synthetic|replay:FILE
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
              "  - `--source audio`          mic knock detection (works on any laptop with a mic; auto picks it)\n"
              "  - `wintap demo`             full pipeline on a simulated laptop\n"
              "  - `pip install wintap[hid]` + a USB IMU breakout (BMI160/BNO055) for real IMU hardware\n"
              "  - on a 2-in-1/convertible/tablet the built-in sensor is picked up automatically")


def cmd_defaults(args):
    app = build_app(args)
    app.set_config({"actions": {"z0": "desktop_left", "z1": "desktop_right",
                                "z2": "play_pause", "z3": "privacy_guard"}})
    print("default 2x2 actions written to config: z0=desktop_left z1=desktop_right z2=play_pause z3=privacy_guard")


def cmd_version(args):
    from . import __version__
    print(f"wintap {__version__}")


def cmd_features(args):
    """Manage feature toggles for tap detection.

    Usage:
      wintap features --list              # list all features
      wintap features --enable N M        # enable features N, M
      wintap features --disable N M        # disable features N, M
      wintap features --reset             # reset to defaults
      wintap features --status            # show enabled/disabled status
    """
    app = build_app(args)
    cfg = app.cfg

    # Import feature definitions
    from .features import FEATURE_CATEGORIES

    # Flatten feature list
    all_features = []
    for cat, features in FEATURE_CATEGORIES.items():
        for f in features:
            all_features.append(f["name"])

    if args.list:
        print("Available features:")
        for cat, features in FEATURE_CATEGORIES.items():
            print(f"  [{cat}]")
            for f in features:
                name = f["name"]
                enabled = cfg.get("enabled_features", []) == [] or name in cfg.get("enabled_features", all_features)
                status = "on" if enabled else "off"
                print(f"    {name}: {status}  ({f['desc']})")
        return

    if args.reset:
        app.set_config({"enabled_features": []})
        print("Features reset to all enabled (default behavior)")
        return

    if args.list_features:
        enabled = cfg.get("enabled_features", [])
        if not enabled:
            enabled = all_features
        disabled = [f for f in all_features if f not in enabled]
        print(f"Enabled features ({len(enabled)}): {', '.join(enabled)}")
        if disabled:
            print(f"Disabled features ({len(disabled)}): {', '.join(disabled)}")
        return

    # Get current enabled state
    enabled_features = set(cfg.get("enabled_features", [])) if cfg.get("enabled_features") else set(all_features)

    if args.enable:
        for name in args.enable:
            if name not in all_features:
                print(f"Warning: '{name}' is not a recognized feature. Skipping.")
            else:
                enabled_features.add(name)
                print(f"Enabled: {name}")

    if args.disable:
        for name in args.disable:
            if name not in all_features:
                print(f"Warning: '{name}' is not a recognized feature. Skipping.")
            elif name in enabled_features:
                enabled_features.discard(name)
                print(f"Disabled: {name}")

    if args.enable or args.disable:
        # If enabled_features is empty, that means use all (default)
        if enabled_features == set(all_features):
            app.set_config({"enabled_features": []})
            print("All features enabled (default)")
        else:
            app.set_config({"enabled_features": sorted(list(enabled_features))})
            print(f"Saved: {len(enabled_features)} features enabled")


def cmd_quickstart(args):
    """Interactive quick-start: noise recording, calibration, training, and live mode."""
    app = build_app(args)
    app.start()
    print("\n=== WinTap QuickStart ===")
    print("This will set up your laptop for tap gestures.\n")

    # Step 1: Check sensors
    st = app.status()
    if not st.get("rates", {}).get("gyro"):
        print("ERROR: No IMU sensor detected. Check that your laptop has a built-in accelerometer/gyroscope.")
        print("Run 'python -m wintap sources' for sensor info.\n")
        return
    print(f"✓ IMU sensor detected ({st['rates'].get('gyro', 0)} Hz)\n")

    # Step 2: Record noise
    print("Step 1: Recording 30 seconds of noise...")
    print("Please make desk knocks, move the lid, and adjust the laptop.")
    print("Press Ctrl+C to skip.\n")
    try:
        input("Press Enter to start noise recording (30s)...")
        app.negatives_start({"seconds": 30})
        run_event_loop(app, until=lambda a: a.status()["mode"] != "negatives", quiet=False)
        print("✓ Noise examples recorded\n")
    except KeyboardInterrupt:
        print("Skipped noise recording\n")

    # Step 3: Calibration
    rows = getattr(args, "rows", 2)
    cols = getattr(args, "cols", 2)
    per_zone = getattr(args, "per_zone", 10)
    print(f"Step 2: Calibrating {rows}x{cols} grid, {per_zone} taps per zone...")
    print(f"Tap the highlighted zone {rows * cols * per_zone} times total.\n")
    app.calibrate_start({"rows": rows, "cols": cols, "per_zone": per_zone, "block": 5})
    run_event_loop(app, until=lambda a: a.status()["mode"] != "calibrate", quiet=True)
    print("\n✓ Calibration done\n")

    # Step 4: Train model
    print("Step 3: Training model...")
    time.sleep(0.5)
    rep = app.train()
    print_report(rep)
    print()

    # Step 5: Start live
    print("Step 4: Starting live mode (Ctrl+C to stop)...")
    print("Tap your lid zones to test. Actions are dry-run (won't execute).\n")
    app.set_config({"actions": {"z0": "desktop_left", "z1": "desktop_right",
                                "z2": "play_pause", "z3": "lock"}})
    try:
        run_event_loop(app)
    except KeyboardInterrupt:
        print("\n✓ QuickStart complete. Your configuration is saved.")


def cmd_autostart(args):
    """Start WinTap automatically at Windows login (on), disable it (off), or show state (status)."""
    import os
    startup = os.path.join(os.environ.get("APPDATA", ""),
                           r"Microsoft\Windows\Start Menu\Programs\Startup")
    bat = os.path.join(startup, "wintap.bat")
    if args.action == "status":
        print(f"autostart: {'ON' if os.path.exists(bat) else 'OFF'}")
        print(f"entry: {bat}")
        return
    if args.action == "on":
        os.makedirs(startup, exist_ok=True)
        exe = sys.executable
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pyw):
            exe = pyw  # no console window at login
        with open(bat, "w", newline="") as f:
            f.write(f'@echo off\r\n"{exe}" -m wintap serve --port {args.port}\r\n')
        print(f"autostart ON -> {bat}")
        print("WinTap starts at next login. Stop a running instance with Ctrl+C, or `wintap autostart off`.")
    else:
        if os.path.exists(bat):
            os.remove(bat)
            print("autostart OFF (startup entry removed; a currently running instance keeps running)")
        else:
            print("autostart already OFF")


def cmd_touch(args):
    app = build_app(args)
    rows, cols = max(1, min(6, args.rows)), max(1, min(6, args.cols))
    app.set_config({"actions": {f"z{i}": "tap" for i in range(rows * cols)}, "actions_enabled": True})
    print(f"touchscreen mode: {rows}x{cols} lid zones now tap the same spots on the screen "
          f"(actions_enabled=true). Calibrate that grid, train, then `wintap live --enable-actions`.")


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
    common.add_argument("--source", default=argparse.SUPPRESS, help="auto|winrt|hid|audio|synthetic|replay:FILE")
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

    sp = sub.add_parser(parents=[common], name="touch", help="map every lid zone to a screen tap (lid as touchscreen)")
    sp.add_argument("--rows", type=int, default=3)
    sp.add_argument("--cols", type=int, default=3)
    sp.set_defaults(fn=cmd_touch)

    sp = sub.add_parser(parents=[common], name="autostart",
                        help="start WinTap automatically at Windows login")
    sp.add_argument("action", choices=["on", "off", "status"])
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(fn=cmd_autostart)

    sp = sub.add_parser(parents=[common], name="demo", help="full pipeline on a simulated laptop (no IMU needed)")
    sp.add_argument("--fast", action="store_true", help="no real-time pacing")
    sp.add_argument("--rows", type=int, default=2)
    sp.add_argument("--cols", type=int, default=2)
    sp.add_argument("--per-zone", type=int, default=6)
    sp.set_defaults(fn=cmd_demo)

    sp = sub.add_parser(parents=[common], name="version", help="show wintap version")
    sp.set_defaults(fn=cmd_version)

    sp = sub.add_parser(parents=[common], name="features", help="manage feature toggles")
    sp.add_argument("--list", action="store_true", help="list all features")
    sp.add_argument("--status", action="store_true", help="show enabled/disabled features")
    sp.add_argument("--list-features", action="store_true", help="show current feature status")
    sp.add_argument("--enable", nargs="*", help="enable specified features")
    sp.add_argument("--disable", nargs="*", help="disable specified features")
    sp.add_argument("--reset", action="store_true", help="reset to all features enabled")
    sp.set_defaults(fn=cmd_features)

    sp = sub.add_parser(parents=[common], name="quickstart", help="interactive setup wizard")
    sp.add_argument("--rows", type=int, default=2, help="grid rows (default 2)")
    sp.add_argument("--cols", type=int, default=2, help="grid columns (default 2)")
    sp.add_argument("--per-zone", type=int, default=10, help="taps per zone (default 10)")
    sp.set_defaults(fn=cmd_quickstart)

    args = p.parse_args()
    if not hasattr(args, "data"):
        args.data = default_data_dir()
    if not hasattr(args, "source"):
        args.source = "auto"
    args.fn(args)


if __name__ == "__main__":
    main()
