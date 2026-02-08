import asyncio
import base64
import io
import os
import numpy as np
import httpx
from PIL import Image
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load environment variables from .env (use .env.example as template)
load_dotenv()


def crop_to_640x640(img: Image.Image, vertical_offset: int = 50) -> Image.Image:
    CROP_SIZE = 640
    width, height = img.size

    left = (width - CROP_SIZE) // 2
    right = left + CROP_SIZE

    top = vertical_offset
    bottom = top + CROP_SIZE

    if bottom > height:
        bottom = height
        top = max(0, height - CROP_SIZE)

    if right > width:
        right = width
        left = max(0, width - CROP_SIZE)

    img_cropped = img.crop((left, top, right, bottom))

    if img_cropped.size != (CROP_SIZE, CROP_SIZE):
        img_cropped = img_cropped.resize((CROP_SIZE, CROP_SIZE), Image.Resampling.LANCZOS)

    return img_cropped


def _frame_to_base64_jpeg(frame: np.ndarray, vertical_offset: int = 50) -> str:
    if frame.shape[2] == 4:
        rgb = frame[..., :3][..., ::-1].copy()
    else:
        rgb = frame[..., ::-1].copy()
    img = Image.fromarray(rgb)
    img_cropped = crop_to_640x640(img, vertical_offset=vertical_offset)
    if img_cropped.mode != "RGB":
        img_cropped = img_cropped.convert("RGB")
    buf = io.BytesIO()
    img_cropped.save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _get_env_config() -> tuple[str, str]:
    api_url = os.getenv("ARROW_API_URL")
    proxy_secret = os.getenv("PROXY_SECRET")
    missing = [k for k, v in [("ARROW_API_URL", api_url), ("PROXY_SECRET", proxy_secret)] if not (v and str(v).strip())]
    if missing:
        raise ValueError(
            f"Missing required env: {', '.join(missing)}. "
            "Set them in .env (see .env.example)."
        )
    return api_url.strip(), proxy_secret.strip()


class ArrowPredictionClient:
    def __init__(self):
        self.api_url, self.proxy_secret = _get_env_config()
        self.loop = None
        self.client = None

    def _get_loop(self):
        if self.loop is None or self.loop.is_closed():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
        return self.loop

    async def _get_client(self):
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client

    def _request_headers(self) -> dict:
        """Headers required by RapidAPI: x-rapidapi-key and x-rapidapi-host."""
        host = urlparse(self.api_url).netloc
        return {
            "Content-Type": "application/json",
            "x-rapidapi-host": host,
            "x-rapidapi-key": self.proxy_secret,
        }

    async def _predict_async(self, image_path: str, vertical_offset: int = 50) -> list[str]:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        img = Image.open(image_path)
        img_cropped = crop_to_640x640(img, vertical_offset=vertical_offset)

        if img_cropped.mode == "RGBA":
            rgb_img = Image.new("RGB", img_cropped.size, (255, 255, 255))
            rgb_img.paste(img_cropped, mask=img_cropped.split()[3])
            img_cropped = rgb_img
        elif img_cropped.mode != "RGB":
            img_cropped = img_cropped.convert("RGB")

        img_bytes = io.BytesIO()
        img_cropped.save(img_bytes, format="JPEG", quality=95)
        image_base64 = base64.b64encode(img_bytes.getvalue()).decode("utf-8")

        client = await self._get_client()
        payload = {"image": image_base64}
        response = await client.post(
            self.api_url, json=payload, headers=self._request_headers()
        )

        if response.status_code == 200:
            data = response.json()
            return data["solution"] if isinstance(data, dict) and "solution" in data else data
        else:
            raise Exception(f"API error {response.status_code}: {response.text}")

    def predict(self, image_path: str, vertical_offset: int = 50) -> list[str]:
        loop = self._get_loop()
        return loop.run_until_complete(self._predict_async(image_path, vertical_offset=vertical_offset))

    async def _predict_from_frame_async(
        self, frame: np.ndarray, vertical_offset: int = 50
    ) -> list[str]:
        image_base64 = _frame_to_base64_jpeg(frame, vertical_offset=vertical_offset)
        client = await self._get_client()
        payload = {"image": image_base64}
        response = await client.post(
            self.api_url, json=payload, headers=self._request_headers()
        )
        if response.status_code == 200:
            data = response.json()
            return data["solution"] if isinstance(data, dict) and "solution" in data else data
        raise Exception(f"API error {response.status_code}: {response.text}")

    def predict_from_frame(
        self, frame: np.ndarray, vertical_offset: int = 50
    ) -> list[str]:
        loop = self._get_loop()
        return loop.run_until_complete(
            self._predict_from_frame_async(frame, vertical_offset=vertical_offset)
        )
