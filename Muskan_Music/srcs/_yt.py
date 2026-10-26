
import asyncio
import os
import re
import time
import logging
import yt_dlp
import aiohttp
import config

from typing import Union
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

try:
    from youtubesearchpython.future import VideosSearch, Playlist
except ImportError:
    VideosSearch = None
    Playlist = None



# ----------------- CONFIGURATION -----------------

DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger(__name__)

API_URL = os.environ.get(
    "SHRUTI_API_URL",
    "https://api.shrutibots.in"
)
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsK0jG7mPzpPWgmr5Zb9K1")

WORKER_FALLBACK_API_URL = os.getenv(
    "WORKER_FALLBACK_API_URL",
    "https://youtubenewapi.skybotsdeveloper.workers.dev"
)
WORKER_FALLBACK_API_KEY = os.getenv(
    "WORKER_FALLBACK_API_KEY",
    "itsmesid"
)


def time_to_seconds(time_str):
    stringt = str(time_str)
    return sum(
        int(x) * 60 ** i
        for i, x in enumerate(reversed(stringt.split(":")))
    )


def get_safe_filename(title: str, default_id: str) -> str:
    if not title:
        return default_id
    return re.sub(r'[\\/*?:"<>|]', "", title).strip() or default_id


def extract_video_id(link: str) -> str:
    if "youtu.be/" in link:
        return link.split("youtu.be/", 1)[1].split("?")[0].split("&")[0]
    if "v=" in link:
        return link.split("v=", 1)[1].split("&")[0]
    return link


async def _async_run(func, *args, **kwargs):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    return await loop.run_in_executor(
        None, lambda: func(*args, **kwargs)
    )


# ----------------- DOWNLOADERS -----------------

async def api_download(
    video_id: str,
    download_type: str,
    title: str = None
) -> str:
    if not API_URL or not API_KEY:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, video_id)
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
        return file_path

    try:
        timeout = aiohttp.ClientTimeout(
            total=600, sock_connect=10, sock_read=15
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_URL}/download",
                params={
                    "url": video_id,
                    "type": "audio" if download_type == "audio" else "video",
                    "api_key": API_KEY,
                },
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    LOGGER.error(f"Shruti API Error: Status {resp.status}")
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            LOGGER.info(f"Downloaded '{title}' from Shruti API")
            return file_path

        LOGGER.warning(f"Shruti API returned an invalid file for '{title}'")

    except asyncio.TimeoutError:
        LOGGER.warning("Shruti API timeout")
    except Exception as e:
        LOGGER.error(f"Shruti API Download Error: {e}")

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    return None


async def worker_api_download(
    video_id: str,
    download_type: str,
    title: str = None
) -> str:
    if not WORKER_FALLBACK_API_URL or not WORKER_FALLBACK_API_KEY:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, f"wk_{video_id}")
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
        return file_path

    try:
        timeout = aiohttp.ClientTimeout(
            total=120, sock_connect=3, sock_read=4
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{WORKER_FALLBACK_API_URL}/download",
                params={
                    "url": video_id,
                    "type": "audio" if download_type == "audio" else "video",
                    "api_key": WORKER_FALLBACK_API_KEY,
                },
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    LOGGER.error(f"Worker API Error: Status {resp.status}")
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(131072):
                        f.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path

        LOGGER.warning(f"Worker API returned an invalid file for '{title}'")

    except asyncio.TimeoutError:
        LOGGER.warning("Worker API timeout")
    except Exception as e:
        LOGGER.error(f"Worker API Download Error: {e}")

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    return None


async def ytdl_fallback_download(
    link: str,
    download_type: str,
    title: str = None
) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    video_id = extract_video_id(link)
    filename = get_safe_filename(title, video_id)
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
        return file_path

    video_format = (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
        "/best[ext=mp4]/best"
    )

    ydl_opts = {
        "format": video_format if download_type == "video" else "bestaudio/best",
        "outtmpl": file_path,
        "quiet": True,
        "no_warnings": True,
        "cookiefile": "cookies.txt",
        "extractor_args": {
            "youtube": ["player_client=ios,tv_embedded"]
        },
        "geo_bypass": True,
        "nocheckcertificate": True,
        "noplaylist": True,
    }

    if download_type == "audio":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        await _async_run(
            yt_dlp.YoutubeDL(ydl_opts).download, [link]
        )

        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            LOGGER.info(f"Downloaded '{title}' using yt-dlp")
            return file_path

    except Exception as e:
        LOGGER.error(f"yt-dlp fallback error: {e}")

    return None


async def spotify_fallback_download(title: str) -> str:
    if not title:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()

    filename = get_safe_filename(clean_title, f"sp_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            async with session.get(
                f"https://api.spotifydown.com/search?q={clean_title}"
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            if data.get("success") and data.get("tracks"):
                download_url = data["tracks"][0].get("downloadUrl")

                if download_url:
                    async with session.get(download_url) as song_resp:
                        if song_resp.status == 200:
                            with open(file_path, "wb") as f:
                                async for chunk in song_resp.content.iter_chunked(131072):
                                    f.write(chunk)

                            if (
                                os.path.exists(file_path)
                                and os.path.getsize(file_path) > 50000
                            ):
                                LOGGER.info(
                                    f"Downloaded '{clean_title}' from Spotify"
                                )
                                return file_path

    except Exception as e:
        LOGGER.error(f"Spotify fallback error: {e}")

    return None


async def jiosaavn_fallback_download(title: str) -> str:
    if not title:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()

    filename = get_safe_filename(clean_title, f"js_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")
    saavn_api = getattr(
        config,
        "JIOSAAVN_API",
        "https://saavn.dev/api/search/songs?query="
    )

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            async with session.get(f"{saavn_api}{clean_title}") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            results = data.get("data", {}).get("results", [])

            if data.get("success") and results:
                download_urls = results[0].get("downloadUrl", [])

                if download_urls:
                    async with session.get(download_urls[-1]["url"]) as song_resp:
                        if song_resp.status == 200:
                            with open(file_path, "wb") as f:
                                async for chunk in song_resp.content.iter_chunked(131072):
                                    f.write(chunk)

                            if (
                                os.path.exists(file_path)
                                and os.path.getsize(file_path) > 50000
                            ):
                                LOGGER.info(
                                    f"Downloaded '{clean_title}' from JioSaavn"
                                )
                                return file_path

    except Exception as e:
        LOGGER.error(f"JioSaavn fallback error: {e}")

    return None


async def soundcloud_fallback_download(title: str) -> str:
    if not title:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()

    filename = get_safe_filename(clean_title, f"sc_{int(time.time())}")
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp3")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": file_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    try:
        await _async_run(
            yt_dlp.YoutubeDL(ydl_opts).download,
            [f"scsearch1:{clean_title}"]
        )

        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            LOGGER.info(f"Downloaded '{clean_title}' from SoundCloud")
            return file_path

    except Exception as e:
        LOGGER.error(f"SoundCloud fallback error: {e}")

    return None


async def download_song(link: str, title: str = None) -> str:
    video_id = extract_video_id(link)
    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            result = await VideosSearch(video_id, limit=1).next()
            if result and result.get("result"):
                title = result["result"][0]["title"]
        except Exception:
            pass

    worker_result = await worker_api_download(video_id, "audio", title)
    if worker_result:
        return worker_result

    api_result = await api_download(video_id, "audio", title)
    if api_result:
        return api_result

    yt_result = await ytdl_fallback_download(link, "audio", title)
    if yt_result:
        return yt_result

    if title:
        for fallback in (
            spotify_fallback_download,
            jiosaavn_fallback_download,
            soundcloud_fallback_download,
        ):
            result = await fallback(title)
            if result:
                return result

    return None


async def download_video(link: str, title: str = None) -> str:
    video_id = extract_video_id(link)
    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            result = await VideosSearch(video_id, limit=1).next()
            if result and result.get("result"):
                title = result["result"][0]["title"]
        except Exception:
            pass

    worker_result = await worker_api_download(video_id, "video", title)
    if worker_result:
        return worker_result

    api_result = await api_download(video_id, "video", title)
    if api_result:
        return api_result

    return await ytdl_fallback_download(link, "video", title)


# ----------------- YOUTUBE API CLASS -----------------

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)

        for message in messages:
            if message.entities:
                text = message.text or message.caption or ""
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        return text[entity.offset:entity.offset + entity.length]

            if message.caption_entities:
                text = message.caption or ""
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
                    if entity.type == MessageEntityType.URL:
                        return text[entity.offset:entity.offset + entity.length]

        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                result = response["result"][0]
                duration_min = result.get("duration")
                duration_sec = time_to_seconds(duration_min) if duration_min else 0

                return (
                    result["title"],
                    duration_min,
                    duration_sec,
                    result["thumbnails"][0]["url"].split("?")[0],
                    result["id"],
                )
        except Exception:
            pass

        try:
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "cookiefile": "cookies.txt",
                "extractor_args": {
                    "youtube": ["player_client=ios,tv_embedded"]
                },
            }

            ydl = yt_dlp.YoutubeDL(ydl_opts)
            query = (
                link if "youtube.com" in link or "youtu.be" in link
                else f"ytsearch1:{link}"
            )
            result = await _async_run(
                ydl.extract_info, query, download=False
            )

            if result and result.get("entries"):
                entry = result["entries"][0]
                vidid = entry.get("id")
                duration_sec = int(entry.get("duration") or 0)
                minutes, seconds = divmod(duration_sec, 60)
                hours, minutes = divmod(minutes, 60)
                duration_min = (
                    f"{hours}:{minutes:02d}:{seconds:02d}"
                    if hours else f"{minutes}:{seconds:02d}"
                )

                return (
                    entry.get("title"),
                    duration_min,
                    duration_sec,
                    f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                    vidid,
                )
        except Exception as e:
            LOGGER.error(f"yt-dlp details fallback failed: {e}")

        return None, None, None, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                return response["result"][0]["title"]
        except Exception:
            pass
        return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                return response["result"][0]["duration"]
        except Exception:
            pass
        return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                return response["result"][0]["thumbnails"][0]["url"].split("?")[0]
        except Exception:
            pass
        return "https://telegra.ph/file/2e3d368e77c449c287430.jpg"

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            downloaded_file = await download_video(link)
            if downloaded_file:
                return 1, downloaded_file
            return 0, "Video download failed"
        except Exception as e:
            return 0, f"Video download error: {e}"

    async def playlist(
        self, link, limit, user_id,
        videoid: Union[bool, str] = None
    ):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            playlist = await _async_run(Playlist.get, link)
        except Exception:
            return []

        ids = []
        for item in (playlist.get("videos") or [])[:limit]:
            if item and item.get("id"):
                ids.append(item["id"])
        return ids

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                item = response["result"][0]
                return {
                    "title": item["title"],
                    "link": item["link"],
                    "vidid": item["id"],
                    "duration_min": item["duration"],
                    "thumb": item["thumbnails"][0]["url"].split("?")[0],
                }, item["id"]
        except Exception:
            pass

        try:
            opts = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "cookiefile": "cookies.txt",
                "extractor_args": {
                    "youtube": ["player_client=ios,tv_embedded"]
                },
            }
            ydl = yt_dlp.YoutubeDL(opts)
            query = (
                link if "youtube.com" in link or "youtu.be" in link
                else f"ytsearch1:{link}"
            )
            result = await _async_run(
                ydl.extract_info, query, download=False
            )

            if result and result.get("entries"):
                entry = result["entries"][0]
                vidid = entry.get("id")
                duration_sec = int(entry.get("duration") or 0)
                minutes, seconds = divmod(duration_sec, 60)
                hours, minutes = divmod(minutes, 60)

                return {
                    "title": entry.get("title"),
                    "link": f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": (
                        f"{hours}:{minutes:02d}:{seconds:02d}"
                        if hours else f"{minutes}:{seconds:02d}"
                    ),
                    "thumb": f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                }, vidid
        except Exception as e:
            LOGGER.error(f"yt-dlp track fallback failed: {e}")

        return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        opts = {
            "quiet": True,
            "cookiefile": "cookies.txt",
            "extractor_args": {
                "youtube": ["player_client=ios,tv_embedded"]
            },
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "-x", "16", "-s", "16", "-k", "1M",
                "--allow-piece-length-change=true"
            ],
        }

        available = []
        try:
            ydl = yt_dlp.YoutubeDL(opts)
            result = await _async_run(
                ydl.extract_info, link, download=False
            )

            if result and result.get("formats"):
                for fmt in result["formats"]:
                    if "dash" not in str(fmt.get("format", "")).lower():
                        available.append({
                            "format": fmt.get("format"),
                            "filesize": fmt.get("filesize"),
                            "format_id": fmt.get("format_id"),
                            "ext": fmt.get("ext"),
                            "format_note": fmt.get("format_note"),
                            "yturl": link,
                        })
        except Exception as e:
            LOGGER.error(f"Format extraction failed: {e}")

        return available, link

    async def slider(
        self, link: str, query_type: int,
        videoid: Union[bool, str] = None
    ):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]

        try:
            response = await VideosSearch(link, limit=10).next()
            results = response.get("result") or []
            item = results[query_type]
            return (
                item["title"],
                item["duration"],
                item["thumbnails"][0]["url"].split("?")[0],
                item["id"],
            )
        except Exception:
            return (
                "Unknown Title",
                "0:00",
                "https://telegra.ph/file/2e3d368e77c449c287430.jpg",
                "None",
            )

    async def download(
        self,
        link: str,
        mystic,
        video: Union[bool, str] = None,
        videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None,
        format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link

        try:
            file_title = title if isinstance(title, str) else None

            if video:
                downloaded_file = await download_video(link, title=file_title)
            else:
                downloaded_file = await download_song(link, title=file_title)

            if downloaded_file:
                return downloaded_file, True
            return None, False

        except Exception as e:
            LOGGER.error(f"Error in YouTubeAPI.download: {e}")
            return None, False

    async def autoplay(
        self,
        last_vidid: str,
        title: str,
        max_duration: int = None
    ):
        import random

        try:
            search_query = f"{title} official audio"
            valid_choices = []

            try:
                response = await VideosSearch(search_query, limit=15).next()
                for item in response.get("result", []):
                    vidid = str(item.get("id") or "")
                    if not vidid or vidid == last_vidid:
                        continue

                    duration_str = str(item.get("duration") or "0:00")
                    try:
                        duration_sec = time_to_seconds(duration_str)
                    except (ValueError, TypeError):
                        duration_sec = 0

                    if duration_sec < 30:
                        continue
                    if max_duration and duration_sec > max_duration:
                        continue

                    valid_choices.append({
                        "vidid": vidid,
                        "title": str(item.get("title", "Unknown Title")).title(),
                        "duration_min": duration_str,
                        "duration_sec": duration_sec,
                    })
            except Exception as e:
                LOGGER.warning(f"Autoplay search failed: {e}")

            if not valid_choices:
                opts = {
                    "quiet": True,
                    "extract_flat": True,
                    "noplaylist": True,
                    "cookiefile": "cookies.txt",
                    "extractor_args": {
                        "youtube": ["player_client=ios,tv_embedded"]
                    },
                }
                ydl = yt_dlp.YoutubeDL(opts)
                result = await _async_run(
                    ydl.extract_info,
                    f"ytsearch10:{search_query}",
                    download=False,
                )

                for entry in (result or {}).get("entries", []):
                    vidid = entry.get("id")
                    if not vidid or vidid == last_vidid:
                        continue

                    try:
                        duration_sec = int(float(entry.get("duration") or 0))
                    except (ValueError, TypeError):
                        duration_sec = 0

                    if duration_sec < 30:
                        continue
                    if max_duration and duration_sec > max_duration:
                        continue

                    minutes, seconds = divmod(duration_sec, 60)
                    hours, minutes = divmod(minutes, 60)
                    duration_str = (
                        f"{hours}:{minutes:02d}:{seconds:02d}"
                        if hours else f"{minutes}:{seconds:02d}"
                    )

                    valid_choices.append({
                        "vidid": vidid,
                        "title": str(entry.get("title", "Unknown Title")).title(),
                        "duration_min": duration_str,
                        "duration_sec": duration_sec,
                    })

            return random.choice(valid_choices) if valid_choices else None

        except Exception as e:
            LOGGER.error(f"YouTube Autoplay Function Error: {e}")
            return None


YouTube = YouTubeAPI()
