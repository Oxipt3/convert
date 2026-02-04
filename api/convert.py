from http.server import BaseHTTPRequestHandler
import json
import requests
from PIL import Image
import io
from datetime import datetime
from urllib.parse import urlparse
import math

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        try:
            # Read the request body
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Parse JSON data
            data = json.loads(post_data.decode('utf-8'))
            image_url = data.get('imageUrl')
            user_key = data.get('key')
            warp_to_fill = data.get('warpToFill', True)  # Default to True for backward compatibility
            
            if not image_url:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error":"Missing 'imageUrl' in request body"}, separators=(',', ':')).encode())
                return
            
            # Log the request
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ip_address = self.client_address[0]
            print(f"{timestamp} - IP: {ip_address} - Key: {user_key} - Warp: {warp_to_fill} - URL: {image_url}")
            
            # Check if it's a Pinterest URL and process accordingly
            parsed_url = urlparse(image_url)
            if 'pinterest.com' in parsed_url.netloc or 'pin.it' in parsed_url.netloc:
                print(f"Detected Pinterest URL, fetching from pintools.app...")
                image_url = self.get_pinterest_image_url(image_url)
                if not image_url:
                    self.send_response(400)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error":"Failed to extract image from Pinterest URL"}, separators=(',', ':')).encode())
                    return
                print(f"Got actual image URL from Pinterest: {image_url}")
            
            print(f"Processing image URL: {image_url}")
            
            # Download the image
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Open the image
            img = Image.open(io.BytesIO(response.content))
            
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            original_width, original_height = img.size
            print(f"Original image size: {original_width}x{original_height}")
            
            if warp_to_fill:
                # Warp to fill: Resize to exactly 1024x1024 (stretches/distorts image)
                img = img.resize((1024, 1024), Image.Resampling.LANCZOS)
                print("Warp to fill: Stretched to 1024x1024")
            else:
                # No warp: Keep original aspect ratio, center on 1024x1024 canvas
                # Calculate scaling to fit within 1024x1024 while preserving aspect ratio
                scale_factor = min(1024 / original_width, 1024 / original_height)
                scaled_width = int(original_width * scale_factor)
                scaled_height = int(original_height * scale_factor)
                
                # Resize image
                img_resized = img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                
                # Create a 1024x1024 blank canvas
                canvas = Image.new('RGB', (1024, 1024), (0, 0, 0))
                
                # Calculate position to center the image
                x_offset = (1024 - scaled_width) // 2
                y_offset = (1024 - scaled_height) // 2
                
                # Paste the resized image onto the canvas
                canvas.paste(img_resized, (x_offset, y_offset))
                img = canvas
                print(f"No warp: Scaled to {scaled_width}x{scaled_height}, positioned at ({x_offset}, {y_offset})")
            
            # Get pixel data
            pixels = list(img.getdata())
            
            # Format the result with NO SPACES - exact format Roblox expects
            result = {
                "Height":1024,
                "Width":1024,
                "Pixels":pixels,
                "OriginalHeight":original_height,
                "OriginalWidth":original_width,
                "Warped":warp_to_fill
            }
            
            # Send response with no spaces in JSON
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Use separators to remove all spaces from JSON
            response_json = json.dumps(result, separators=(',', ':'))
            self.wfile.write(response_json.encode())
            
            print(f"Successfully processed image: 1024x1024, {len(pixels)} pixels")
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to download image: {str(e)}"
            print(error_msg)
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error":error_msg}, separators=(',', ':')).encode())
        except Exception as e:
            error_msg = f"Failed to process image: {str(e)}"
            print(error_msg)
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error":error_msg}, separators=(',', ':')).encode())
    
    def get_pinterest_image_url(self, pinterest_url):
        """
        Extract actual image URL from Pinterest URL using pintools.app
        """
        try:
            # Prepare the request to pintools.app
            pintools_url = "https://pintools.app/get-video"
            payload = {"url": pinterest_url}
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            print(f"Making request to pintools.app for Pinterest URL...")
            response = requests.post(
                pintools_url, 
                json=payload, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            print(f"pintools.app response: {result}")
            
            # The response contains contentType, originalUrl, and videoUrl (which is actually an image URL)
            # Check if contentType is "image" and get the videoUrl
            if result.get('contentType') == 'image' and 'videoUrl' in result:
                return result['videoUrl']
            else:
                print(f"Unexpected response format from pintools.app: {result}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error calling pintools.app: {str(e)}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing pintools.app response: {str(e)}")
            return None
        except Exception as e:
            print(f"Unexpected error processing Pinterest URL: {str(e)}")
            return None