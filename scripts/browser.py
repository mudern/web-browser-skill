import argparse
import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


STATE_FILE = "playwright_state.json"


def ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, **data}


def err(message: str, detail: Optional[str] = None, status: int = 400) -> Dict[str, Any]:
    payload = {"ok": False, "error": message}
    if detail:
        payload["detail"] = detail
    payload["status"] = status
    return payload


class BrowserBridge:
    def __init__(self) -> None:
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.lock = threading.RLock()

    def start(
        self,
        headless: bool = False,
        storage_state: Optional[str] = None,
        viewport: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        with self.lock:
            if self.browser:
                return {"message": "already_started"}

            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )

            kwargs: Dict[str, Any] = {}
            if viewport:
                kwargs["viewport"] = viewport

            if storage_state and os.path.exists(storage_state):
                kwargs["storage_state"] = storage_state

            self.context = self.browser.new_context(**kwargs)
            self.page = self.context.new_page()

            return {"message": "started"}

    def ensure_page(self) -> None:
        if not self.page:
            raise RuntimeError("browser not started; call start first")

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.goto(url, wait_until=wait_until, timeout=timeout)
            return self.snapshot()

    def wait(self, ms: int) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.wait_for_timeout(ms)
            return {"message": f"waited_{ms}ms"}

    def press(self, selector: str, key: str, timeout: int = 10000) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.locator(selector).first.press(key, timeout=timeout)
            return self.snapshot()

    def fill(self, selector: str, value: str, timeout: int = 10000) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.locator(selector).first.fill(value, timeout=timeout)
            return self.snapshot()

    def click(self, selector: str, timeout: int = 10000) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.locator(selector).first.click(timeout=timeout)
            return self.snapshot()

    def save_state(self, path: str = STATE_FILE) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.context.storage_state(path=path)
            return {"message": "state_saved", "path": path}

    def load_state(self, path: str = STATE_FILE, headless: bool = False) -> Dict[str, Any]:
        with self.lock:
            self.close()
            return self.start(headless=headless, storage_state=path)

    def screenshot(self, path: str = "page.png", full_page: bool = True) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            self.page.screenshot(path=path, full_page=full_page)
            return {"message": "screenshot_saved", "path": path}

    def eval(self, script: str) -> Dict[str, Any]:
        with self.lock:
            self.ensure_page()
            result = self.page.evaluate(script)
            return {"result": result}

    def snapshot(self) -> Dict[str, Any]:
        self.ensure_page()

        js = """
        () => {
          const bodyText = (document.body?.innerText || "").trim().slice(0, 4000);

          const nodes = Array.from(document.querySelectorAll(
            'a, button, input, textarea, select, [role="button"]'
          ));

          const elements = nodes.slice(0, 80).map((el, idx) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const visible =
              rect.width > 0 &&
              rect.height > 0 &&
              style.visibility !== 'hidden' &&
              style.display !== 'none';

            return {
              index: idx,
              tag: el.tagName.toLowerCase(),
              text: (el.innerText || el.value || "").trim().slice(0, 200),
              placeholder: el.placeholder || "",
              type: el.type || "",
              name: el.name || "",
              id: el.id || "",
              class: (el.className || "").toString().slice(0, 200),
              href: el.href || "",
              visible,
              selector_hint:
                el.id ? `#${el.id}` :
                el.getAttribute('name') ? `${el.tagName.toLowerCase()}[name="${el.getAttribute('name')}"]` :
                el.tagName.toLowerCase()
            };
          }).filter(x => x.visible);

          return {
            title: document.title,
            url: location.href,
            text: bodyText,
            elements
          };
        }
        """
        with self.lock:
            data = self.page.evaluate(js)
            return data

    def close(self) -> Dict[str, Any]:
        with self.lock:
            if self.page:
                try:
                    self.page.close()
                except Exception:
                    pass
                self.page = None

            if self.context:
                try:
                    self.context.close()
                except Exception:
                    pass
                self.context = None

            if self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass
                self.browser = None

            if self.pw:
                try:
                    self.pw.stop()
                except Exception:
                    pass
                self.pw = None

            return {"message": "closed"}

    def handle(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        action = cmd.get("action")
        if not action:
            raise ValueError("missing action")

        if action == "start":
            return self.start(
                headless=cmd.get("headless", False),
                storage_state=cmd.get("storage_state"),
                viewport=cmd.get("viewport"),
            )
        if action == "goto":
            return self.goto(
                url=cmd["url"],
                wait_until=cmd.get("wait_until", "domcontentloaded"),
                timeout=cmd.get("timeout", 30000),
            )
        if action == "snapshot":
            return self.snapshot()
        if action == "click":
            return self.click(cmd["selector"], timeout=cmd.get("timeout", 10000))
        if action == "fill":
            return self.fill(cmd["selector"], cmd["value"], timeout=cmd.get("timeout", 10000))
        if action == "press":
            return self.press(cmd["selector"], cmd["key"], timeout=cmd.get("timeout", 10000))
        if action == "wait":
            return self.wait(cmd.get("ms", 1000))
        if action == "save_state":
            return self.save_state(cmd.get("path", STATE_FILE))
        if action == "load_state":
            return self.load_state(
                path=cmd.get("path", STATE_FILE),
                headless=cmd.get("headless", False),
            )
        if action == "screenshot":
            return self.screenshot(
                path=cmd.get("path", "page.png"),
                full_page=cmd.get("full_page", True),
            )
        if action == "eval":
            return self.eval(cmd["script"])
        if action == "close":
            return self.close()

        raise ValueError(f"unknown action: {action}")


class BrowserRequestHandler(BaseHTTPRequestHandler):
    bridge: BrowserBridge = None  # type: ignore

    def _send_json(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(ok({"message": "ok"}))
            return

        if parsed.path == "/snapshot":
            try:
                result = self.bridge.snapshot()
                self._send_json(ok(result))
            except PlaywrightTimeoutError as e:
                self._send_json(err("playwright timeout", str(e), 504), 504)
            except Exception as e:
                self._send_json(err(str(e), traceback.format_exc(limit=3), 500), 500)
            return

        if parsed.path == "/action":
            params = parse_qs(parsed.query)
            action = params.get("action", [None])[0]
            if not action:
                self._send_json(err("missing action query parameter", status=400), 400)
                return

            cmd: Dict[str, Any] = {"action": action}
            for key, value in params.items():
                if key == "action":
                    continue
                cmd[key] = value[0] if len(value) == 1 else value

            try:
                result = self.bridge.handle(cmd)
                self._send_json(ok(result))
            except PlaywrightTimeoutError as e:
                self._send_json(err("playwright timeout", str(e), 504), 504)
            except Exception as e:
                self._send_json(err(str(e), traceback.format_exc(limit=3), 500), 500)
            return

        self._send_json(err("not found", status=404), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != "/action":
            self._send_json(err("not found", status=404), 404)
            return

        try:
            cmd = self._read_json_body()
            result = self.bridge.handle(cmd)
            self._send_json(ok(result))
        except json.JSONDecodeError as e:
            self._send_json(err("invalid json body", str(e), 400), 400)
        except PlaywrightTimeoutError as e:
            self._send_json(err("playwright timeout", str(e), 504), 504)
        except Exception as e:
            self._send_json(err(str(e), traceback.format_exc(limit=3), 500), 500)

    def log_message(self, format: str, *args: Any) -> None:
        # 少点噪音；需要日志再改成 print
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Playwright browser local HTTP service")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    bridge = BrowserBridge()
    BrowserRequestHandler.bridge = bridge

    server = HTTPServer((args.host, args.port), BrowserRequestHandler)

    print(f"Web browser service listening on http://{args.host}:{args.port}", flush=True)
    print("POST /action 发送 JSON 命令；GET /health 检查服务状态；GET /snapshot 获取页面快照", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            bridge.close()
        except Exception:
            pass
        server.server_close()


if __name__ == "__main__":
    main()
