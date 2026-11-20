"""Ejecuta intercambios TCP entre tres nodos y exporta sus mediciones."""

import argparse
import socket
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from threading import Barrier, Thread
from time import perf_counter
from uuid import uuid4

from server import EVENT_FIELDS, PORTS, Node, NodeServer, receive_frame, write_csv

ROUTES = (("nodo-A", "nodo-B"), ("nodo-B", "nodo-C"), ("nodo-C", "nodo-A"))
LATENCY_FIELDS = (
    "run_id", "message_id", "sender", "receiver", "payload_bytes", "rtt_ms", "mode",
)


def exchange(connection, node, peer, run_id, message_id, message, mode):
    started = perf_counter()
    node.send(
        connection, peer, run_id=run_id, message_id=message_id, kind="request", message=message,
    )
    response = receive_frame(connection)
    finished = perf_counter()
    if (
        response is None
        or response["sender"] != peer
        or response["run_id"] != run_id
        or response["message_id"] != message_id
        or response["kind"] != "response"
        or response["message"] != message
    ):
        raise ValueError(f"Respuesta inesperada para {message_id}")
    node.receive(response)
    return {
        "run_id": run_id, "message_id": message_id, "sender": node.name, "receiver": peer,
        "payload_bytes": len(message), "rtt_ms": f"{(finished - started) * 1000:.6f}",
        "mode": mode,
    }


def run(args, events_path, latencies_path):
    nodes = {name: Node(name) for name in PORTS}
    message = "x" * args.size
    run_id = uuid4().hex
    mode = "concurrent" if args.concurrent else "sequential"

    with ExitStack() as stack:
        for name, node in nodes.items():
            server = stack.enter_context(NodeServer((args.host, PORTS[name]), node))
            thread = Thread(target=server.serve_forever)
            thread.start()
            stack.callback(thread.join)
            stack.callback(server.shutdown)
            print(f"{name} escucha en {args.host}:{PORTS[name]}", flush=True)

        connections = {}
        for sender, peer in ROUTES:
            connection = stack.enter_context(
                socket.create_connection((args.host, PORTS[peer]), timeout=10)
            )
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connections[sender] = connection

        def send_one(index, route, barrier=None):
            sender, peer = route
            if barrier is not None:
                barrier.wait()
            return exchange(
                connections[sender], nodes[sender], peer, run_id, f"{index + 1:04d}",
                message, mode,
            )

        started = perf_counter()
        if not args.concurrent:
            rows = [send_one(i, ROUTES[i % len(ROUTES)]) for i in range(args.count)]
        else:
            rows = []
            with ThreadPoolExecutor(max_workers=len(ROUTES)) as pool:
                for offset in range(0, args.count, len(ROUTES)):
                    batch = ROUTES[:args.count - offset]
                    barrier = Barrier(len(batch), timeout=10)
                    jobs = [pool.submit(send_one, offset + i, route, barrier)
                            for i, route in enumerate(batch)]
                    rows.extend(job.result() for job in jobs)
        elapsed = perf_counter() - started

    events = [event for node in nodes.values() for event in node.events]
    write_csv(events_path, EVENT_FIELDS, events)
    write_csv(latencies_path, LATENCY_FIELDS, rows)
    print(f"{len(rows)} intercambios | {args.size} B | {mode} | {len(events)} eventos locales")
    print(f"Duración: {elapsed:.6f} s | Rendimiento: {len(rows) / elapsed:.2f} intercambios/s")
    print(f"Eventos: {events_path}\nLatencias: {latencies_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--size", type=int, default=100, choices=(100, 10240))
    parser.add_argument("--concurrent", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="Prefijo de los archivos CSV")
    args = parser.parse_args()
    if args.count < 1:
        parser.error("Use un conteo positivo")
    events = args.output.with_name(f"{args.output.name}_eventos.csv")
    latencies = args.output.with_name(f"{args.output.name}_latencias.csv")
    if events.exists() or latencies.exists():
        parser.error("Elija un prefijo sin archivos previos")
    run(args, events, latencies)


if __name__ == "__main__":
    main()
