#!/usr/bin/env python3
import argparse
import queue
import socket
import sys
import threading
import time

try:
    import traci
except ImportError:
    sys.exit("traci not found. export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH")

event_queue = queue.Queue()


def handle_client(conn, args):
    f = conn.makefile("rwb", buffering=0)
    while True:
        line = f.readline()
        if not line:
            break
        line = line.decode().strip()
        if not line:
            continue

        if line == "STEP":
            traci.simulationStep()
            t = traci.simulation.getTime()
            out = []
            for veh_id in traci.vehicle.getIDList():
                x, y = traci.vehicle.getPosition(veh_id)
                angle = traci.vehicle.getAngle(veh_id)
                speed = traci.vehicle.getSpeed(veh_id)
                lane = traci.vehicle.getLaneID(veh_id)
                out.append(f"VEH {veh_id} {x:.3f} {y:.3f} {angle:.2f} {speed:.3f} {lane}\n")
            out.append(f"END {t:.3f}\n\n")
            f.write("".join(out).encode())
            f.flush()

        elif line.startswith("BREAKDOWN "):
            veh_id = line.split(" ", 1)[1].strip()
            try:
                traci.vehicle.setSpeed(veh_id, 0)
                x, y = traci.vehicle.getPosition(veh_id)
                lane = traci.vehicle.getLaneID(veh_id)
                f.write(f"OK BREAKDOWN {veh_id}\n\n".encode())
                print(f"[BRIDGE] Live breakdown issued for {veh_id} at t={traci.simulation.getTime():.1f}s "
                      f"pos=({x:.1f},{y:.1f}) lane={lane}")
            except traci.exceptions.TraCIException as e:
                f.write(f"ERR BREAKDOWN {veh_id} {e}\n\n".encode())
            f.flush()

        elif line.startswith("ACTION "):
            # ACTION <vehId> <hazardVehId>: warned vehicle reacts to a stopped vehicle ahead
            try:
                _, veh_id, hz_id = line.split()
                cur = traci.vehicle.getSpeed(veh_id)
                lane_id = traci.vehicle.getLaneID(veh_id)
                edge = traci.vehicle.getRoadID(veh_id)
                idx = traci.vehicle.getLaneIndex(veh_id)
                done = []
                # React only if the stopped vehicle is on this car's remaining route.
                # In a street grid a car on a crossing, parallel or opposite street can be
                # "ahead" in straight-line terms but never reaches the hazard.
                try:
                    upcoming = traci.vehicle.getRoute(veh_id)[traci.vehicle.getRouteIndex(veh_id):]
                    on_route = traci.vehicle.getRoadID(hz_id) in upcoming
                except Exception:
                    on_route = False
                if not on_route:
                    done.append("NO ACTION (hazard not on its route)")
                else:
                    try:
                        same_lane = (traci.vehicle.getLaneID(hz_id) == lane_id)
                    except Exception:
                        same_lane = False
                    if same_lane and not edge.startswith(":"):
                        n = traci.edge.getLaneNumber(edge)
                        tgt = idx + 1 if idx + 1 < n else idx - 1
                        if 0 <= tgt < n and tgt != idx:
                            traci.vehicle.changeLane(veh_id, tgt, 10.0)
                            done.append(f"CHANGE LANE {idx}->{tgt}")
                    new_speed = max(5.0, 0.5 * cur)
                    traci.vehicle.slowDown(veh_id, new_speed, 5.0)
                    done.append(f"SLOW DOWN {cur:.1f}->{new_speed:.1f} m/s")
                msg = " + ".join(done)
                print(f"[BRIDGE] Hazard action for {veh_id} (stopped {hz_id} ahead): {msg}", flush=True)
                f.write(f"OK ACTION {msg}\n\n".encode())
            except Exception as e:
                f.write(f"ERR ACTION {e}\n\n".encode())
            if hasattr(f, "flush"):
                f.flush()
        elif line.startswith("EVENT "):
            try:
                _, xs, ys, text = line.split(" ", 3)
                float(xs), float(ys)  # validated but unused -- dashboard is position-free
                t = traci.simulation.getTime()
                event_queue.put((t, label_names(text)))
                f.write(b"OK EVENT\n\n")
            except ValueError as e:
                f.write(f"ERR EVENT {e}\n\n".encode())
            f.flush()

        elif line == "QUIT":
            f.write(b"OK QUIT\n\n")
            f.flush()
            break

        else:
            f.write(f"ERR unknown command: {line}\n\n".encode())
            f.flush()

    conn.close()


def sumo_server_loop(args):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", args.bridge_port))
    srv.listen(1)
    print(f"[BRIDGE] Listening for ns-3 (or a test client) on 127.0.0.1:{args.bridge_port} ...")

    try:
        while True:
            conn, addr = srv.accept()
            print(f"[BRIDGE] Client connected from {addr}")
            handle_client(conn, args)
            print("[BRIDGE] Client disconnected.")
    except (KeyboardInterrupt, OSError):
        pass
    finally:
        traci.close()
        srv.close()


NAME_MAP = {}  # ns-3 vehicle index -> SUMO vehicle id (from --node-map)


def label_names(msg):
    """'Vehicle6 broke down' -> 'Vehicle6 (veh4) broke down' (display only)."""
    if not NAME_MAP:
        return msg
    import re
    return re.sub(r"\bVehicle(\d+)\b",
                  lambda m: f"Vehicle{m.group(1)} ({NAME_MAP.get(int(m.group(1)), '?')})", msg)


def run_dashboard():
    import tkinter as tk

    root = tk.Tk()
    root.title("Live Co-Sim Events")
    root.geometry("620x380+40+40")
    root.attributes("-topmost", True)

    header = tk.Label(root, text="NDN-VANET Live Co-Sim -- Key Events",
                       bg="black", fg="#00ff66", font=("Courier", 11, "bold"))
    header.pack(fill="x")

    text = tk.Text(root, bg="black", fg="#00ff66", font=("Courier", 11),
                    wrap="word", state="disabled")
    text.pack(fill="both", expand=True)

    max_lines = 20

    def poll():
        while True:
            try:
                t, msg = event_queue.get_nowait()
            except queue.Empty:
                break
            text.configure(state="normal")
            text.insert("end", f"[t={t:6.1f}s] {msg}\n")
            num_lines = int(text.index("end-1c").split(".")[0])
            if num_lines > max_lines:
                text.delete("1.0", f"{num_lines - max_lines + 1}.0")
            text.see("end")
            text.configure(state="disabled")
        root.after(200, poll)

    root.after(200, poll)
    root.mainloop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sumocfg", required=True)
    ap.add_argument("--sumo-binary", default="sumo-gui")
    ap.add_argument("--sumo-port", type=int, default=8813)
    ap.add_argument("--bridge-port", type=int, default=9001)
    ap.add_argument("--gui-settings", default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--no-dashboard", action="store_true",
                     help="disable the Tk event dashboard window")
    ap.add_argument("--node-map", default=None,
                     help="<scenario>_node_map.csv: show SUMO names next to ns-3 names in the events window")
    args = ap.parse_args()
    if args.node_map:
        import csv
        for r in csv.DictReader(open(args.node_map)):
            NAME_MAP[int(r["ns3_node_index"])] = r["sumo_vehicle_id"]
        print(f"[BRIDGE] Name map loaded: {len(NAME_MAP)} vehicles (events window shows ns-3 and SUMO names)")

    cmd = [args.sumo_binary, "-c", args.sumocfg]
    if args.gui_settings:
        cmd += ["--gui-settings-file", args.gui_settings]
    if args.end is not None:
        cmd += ["--end", str(args.end)]

    print(f"[BRIDGE] Launching {' '.join(cmd)} on TraCI port {args.sumo_port} ...")
    traci.start(cmd, port=args.sumo_port)
    print("[BRIDGE] SUMO started. Waiting for a bridge client to connect ...")

    server_thread = threading.Thread(target=sumo_server_loop, args=(args,), daemon=True)
    server_thread.start()

    if args.no_dashboard:
        try:
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("[BRIDGE] Stopped by user.")
    else:
        run_dashboard()


if __name__ == "__main__":
    main()
