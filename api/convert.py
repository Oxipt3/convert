from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import requests
from PIL import Image
import io
from datetime import datetime
from urllib.parse import urlparse, unquote

PORT = 10000
HOST = "0.0.0.0"


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            image_url = data.get("imageUrl")
            user_key = data.get("key")
            warp_to_fill = data.get("warpToFill", True)

            if not image_url:
                self.send_json(400, {"error": "Missing imageUrl"})
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ip = self.client_address[0]

            print(f"[{timestamp}] IP={ip} KEY={user_key} WARP={warp_to_fill}")
            print(f"IMAGE URL => {image_url}")

            parsed_url = urlparse(image_url)

            # ---------------- Google Share Support ----------------
            if "share.google" in parsed_url.netloc:
                print("Google Share detected — extracting real image...")
                image_url = self.get_google_share_image_url(image_url)

                if not image_url:
                    self.send_json(400, {"error": "Google Share extract failed"})
                    return

            # ---------------- Pinterest Support ----------------
            if "pinterest.com" in parsed_url.netloc or "pin.it" in parsed_url.netloc:
                print("Pinterest detected — extracting real image...")
                image_url = self.get_pinterest_image_url(image_url)

                if not image_url:
                    self.send_json(400, {"error": "Pinterest extract failed"})
                    return

            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()

            img = Image.open(io.BytesIO(response.content))
            if img.mode != "RGB":
                img = img.convert("RGB")

            ow, oh = img.size

            if warp_to_fill:
                img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
            else:
                scale = min(1024 / ow, 1024 / oh)
                nw = int(ow * scale)
                nh = int(oh * scale)
                resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (1024, 1024), (0, 0, 0))
                x = (1024 - nw) // 2
                y = (1024 - nh) // 2
                canvas.paste(resized, (x, y))
                img = canvas

            pixels = list(img.getdata())

            result = {
                "Height": 1024,
                "Width": 1024,
                "Pixels": pixels,
                "OriginalHeight": oh,
                "OriginalWidth": ow,
                "Warped": warp_to_fill
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, separators=(",", ":")).encode())

            print("SUCCESS -> Returned", len(pixels), "pixels")

        except requests.exceptions.RequestException as e:
            print("DOWNLOAD ERROR:", e)
            self.send_json(400, {"error": "Failed to download image"})
        except Exception as e:
            print("SERVER ERROR:", e)
            self.send_json(500, {"error": "Server processing error"})

    def send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, separators=(",", ":")).encode())

    # ---------------- Google Share Helper ----------------
    def get_google_share_image_url(self, share_url):
        try:
            url = share_url
            while True:
                response = requests.get(url, allow_redirects=False)
                redirect_url = response.headers.get("Location")
                if not redirect_url:
                    break
                if "?imgurl=" in redirect_url or "&imgurl=" in redirect_url:
                    if "?imgurl=" in redirect_url:
                        img_part = redirect_url.split("?imgurl=")[1].split("&")[0]
                    else:
                        img_part = redirect_url.split("&imgurl=")[1].split("&")[0]
                    return unquote(img_part)
                url = redirect_url
            return None
        except Exception as e:
            print("GOOGLE SHARE ERROR:", e)
            return None

    # ---------------- Pinterest Helper ----------------
    def get_pinterest_image_url(self, pinterest_url):
        try:
            api_url = "https://pintools.app/get-video"
            payload = {"url": pinterest_url}
            headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            if data.get("contentType") == "image" and "videoUrl" in data:
                return data["videoUrl"]
            return None
        except Exception as e:
            print("PINTEREST ERROR:", e)
            return None


if __name__ == "__main__":
    print("Starting server...")
    server = ThreadingHTTPServer((HOST, PORT), handler)
    print(f"Server running on http://{HOST}:{PORT}")
    server.serve_forever()
