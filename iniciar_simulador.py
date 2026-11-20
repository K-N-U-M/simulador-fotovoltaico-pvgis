#!/usr/bin/env python3
"""Servidor local y proxy CORS para el Simulador Fotovoltaico PVGIS."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import json
import sys

HOST = "127.0.0.1"
PORT = 8080
PVGIS_ENDPOINT = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
HTML_PATH = Path(__file__).with_name("simulador_fotovoltaico_pvgis.html")

ALLOWED_PARAMS = {
    "lat",
    "lon",
    "peakpower",
    "loss",
    "angle",
    "aspect",
    "pvtechchoice",
    "mountingplace",
    "raddatabase",
    "startyear",
    "endyear",
    "outputformat",
}

CACHE: dict[str, bytes] = {}


class SimulatorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/simulador_fotovoltaico_pvgis.html"):
            self._serve_html()
            return
        if parsed.path == "/api/pvgis":
            self._proxy_pvgis(parsed.query)
            return
        self._send_json(404, {"error": "Ruta no encontrada"})

    def _serve_html(self) -> None:
        if not HTML_PATH.exists():
            self._send_json(500, {"error": f"No se encontró {HTML_PATH.name}"})
            return
        data = HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _proxy_pvgis(self, raw_query: str) -> None:
        params = parse_qs(raw_query, keep_blank_values=False)
        filtered = {
            k: v[0] for k, v in sorted(params.items()) if k in ALLOWED_PARAMS and v
        }
        filtered["outputformat"] = "json"
        query_str = urlencode(filtered)

        if query_str in CACHE:
            self._send_bytes(200, CACHE[query_str], "application/json; charset=utf-8")
            return

        url = f"{PVGIS_ENDPOINT}?{query_str}"
        req = Request(url, headers={"User-Agent": "RA-PV-Simulator/1.0"})
        try:
            with urlopen(req, timeout=15) as resp:
                body = resp.read()
                CACHE[query_str] = body
                self._send_bytes(resp.status, body, "application/json; charset=utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            self._send_json(exc.code, {"error": f"PVGIS HTTP {exc.code}", "detail": detail})
        except URLError as exc:
            self._send_json(502, {"error": f"Error de conexión con PVGIS: {exc.reason}"})

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = ThreadingHTTPServer((HOST, port), SimulatorHandler)
    print(f"Simulador fotovoltaico activo en http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
