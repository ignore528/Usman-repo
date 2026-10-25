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
from youtubesearchpython.future import VideosSearch, Playlist

DOWNLOAD_DIR = "downloads"
LOGGER = logging.getLogger(__name__)

API_URL = os.environ.get("SHRUTI_API_URL", "https://api.shrutibots.site")
API_KEY = os.environ.get("SHRUTI_API_KEY", "ShrutiBotsK0jG7mPzpPWgmr5Zb9K1")

WORKER_FALLBACK_API_URL = os.getenv(
    "WORKER_FALLBACK_API_URL",
    "https://youtubenewapi.skybotsdeveloper.workers.dev",
)
WORKER_FALLBACK_API_KEY = os.getenv("WORKER_FALLBACK_API_KEY", "")


def time_to_seconds(time_str):
    try:
        return sum(
            int(value) * 60 ** index
            for index, value in enumerate(reversed(str(time_str).split(":")))
        )
    except (ValueError, TypeError):
        return 0


def get_safe_filename(title: str, default_id: str) -> str:
    title = title or default_id
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(title)).strip()
    return cleaned or default_id


def extract_video_id(link: str) -> str:
    link = str(link).strip()
    if "youtu.be/" in link:
        return link.split("youtu.be/", 1)[1].split("?")[0].split("/")[0]
    if "youtube.com/shorts/" in link:
        return link.split("youtube.com/shorts/", 1)[1].split("?")[0]
    if "youtube.com/live/" in link:
        return link.split("youtube.com/live/", 1)[1].split("?")[0]
    if "v=" in link:
        return link.split("v=", 1)[1].split("&")[0]
    return link


async def _async_run(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def _api_download(
    base_url: str, api_key: str, video_id: str,
    download_type: str, title: str = None, prefix: str = ""
) -> str:
    if not base_url or not api_key:
        return None

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = get_safe_filename(title, f"{prefix}{video_id}")
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
        return file_path

    timeout = aiohttp.ClientTimeout(total=600, sock_connect=10, sock_read=30)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{base_url.rstrip('/')}/download",
                params={
                    "url": video_id,
                    "type": download_type,
                    "api_key": api_key,
                },
            ) as response:
                if response.status != 200:
                    LOGGER.error("%s API status: %s", prefix or "Download", response.status)
                    return None
                with open(file_path, "wb") as output:
                    async for chunk in response.content.iter_chunked(131072):
                        output.write(chunk)

        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            LOGGER.info("Download succeeded for %s", title or video_id)
            return file_path
        LOGGER.warning("API returned an empty or small file for %s", title or video_id)
    except Exception as error:
        LOGGER.error("%s API download error: %s", prefix or "Download", error)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
    return None


async def api_download(video_id: str, download_type: str, title: str = None) -> str:
    return await _api_download(
        API_URL, API_KEY, video_id, download_type, title, "Shruti"
    )


async def worker_api_download(
    video_id: str, download_type: str, title: str = None
) -> str:
    return await _api_download(
        WORKER_FALLBACK_API_URL, WORKER_FALLBACK_API_KEY,
        video_id, download_type, title, "wk_"
    )


async def ytdl_fallback_download(
    link: str, download_type: str, title: str = None
) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    video_id = extract_video_id(link)
    filename = get_safe_filename(title, video_id)
    ext = "mp4" if download_type == "video" else "mp3"
    file_path = os.path.join(DOWNLOAD_DIR, f"{filename}.{ext}")

    if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
        return file_path

    ydl_opts = {
        "format": (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            if download_type == "video" else "bestaudio/best"
        ),
        "outtmpl": file_path,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
    }
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"
    if download_type == "audio":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        await _async_run(yt_dlp.YoutubeDL(ydl_opts).download, [link])
        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path
    except Exception as error:
        LOGGER.error("yt-dlp download error: %s", error)
    return None


async def spotify_fallback_download(title: str) -> str:
    if not title:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()
    file_path = os.path.join(
        DOWNLOAD_DIR, f"{get_safe_filename(clean_title, f'sp_{int(time.time())}')}.mp3"
    )
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://api.spotifydown.com/search", params={"q": clean_title}
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
            tracks = data.get("tracks") or []
            if not data.get("success") or not tracks:
                return None
            download_url = tracks[0].get("downloadUrl")
            if not download_url:
                return None
            async with session.get(download_url) as response:
                if response.status != 200:
                    return None
                with open(file_path, "wb") as output:
                    async for chunk in response.content.iter_chunked(131072):
                        output.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path
    except Exception as error:
        LOGGER.error("Spotify fallback error: %s", error)
    return None


async def jiosaavn_fallback_download(title: str) -> str:
    if not title:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()
    file_path = os.path.join(
        DOWNLOAD_DIR, f"{get_safe_filename(clean_title, f'js_{int(time.time())}')}.mp3"
    )
    api_base = getattr(
        config, "JIOSAAVN_API",
        "https://saavn.dev/api/search/songs?query="
    )
    search_url = f"{api_base}{clean_title}"
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            async with session.get(search_url) as response:
                if response.status != 200:
                    return None
                data = await response.json()
            results = data.get("data", {}).get("results", [])
            if not results:
                return None
            urls = results[0].get("downloadUrl", [])
            if not urls:
                return None
            best_url = urls[-1].get("url")
            if not best_url:
                return None
            async with session.get(best_url) as response:
                if response.status != 200:
                    return None
                with open(file_path, "wb") as output:
                    async for chunk in response.content.iter_chunked(131072):
                        output.write(chunk)
        if os.path.exists(file_path) and os.path.getsize(file_path) > 50000:
            return file_path
    except Exception as error:
        LOGGER.error("JioSaavn fallback error: %s", error)
    return None


async def soundcloud_fallback_download(title: str) -> str:
    if not title:
        return None
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    clean_title = re.sub(
        r"\(.*?\)|\[.*?\]|official|video|audio|lyric",
        "", title, flags=re.IGNORECASE
    ).strip()
    file_path = os.path.join(
        DOWNLOAD_DIR, f"{get_safe_filename(clean_title, f'sc_{int(time.time())}')}.mp3"
    )
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
            return file_path
    except Exception as error:
        LOGGER.error("SoundCloud fallback error: %s", error)
    return None


async def download_song(link: str, title: str = None) -> str:
    video_id = extract_video_id(link)
    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            result = await VideosSearch(video_id, limit=1).next()
            if result and result.get("result"):
                title = result["result"][0].get("title")
        except Exception:
            pass

    for downloader in (worker_api_download, api_download):
        path = await downloader(video_id, "audio", title)
        if path:
            return path

    path = await ytdl_fallback_download(link, "audio", title)
    if path:
        return path

    if title:
        for downloader in (
            spotify_fallback_download,
            jiosaavn_fallback_download,
            soundcloud_fallback_download,
        ):
            path = await downloader(title)
            if path:
                return path
    return None


async def download_video(link: str, title: str = None) -> str:
    video_id = extract_video_id(link)
    if not video_id or len(video_id) < 3:
        return None

    if not title:
        try:
            result = await VideosSearch(video_id, limit=1).next()
            if result and result.get("result"):
                title = result["result"][0].get("title")
        except Exception:
            pass

    path = await worker_api_download(video_id, "video", title)
    if path:
        return path
    path = await api_download(video_id, "video", title)
    if path:
        return path
    return await ytdl_fallback_download(link, "video", title)


class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        for message in messages:
            entities = message.entities or message.caption_entities or []
            text_value = message.text or message.caption or ""
            for entity in entities:
                if entity.type == MessageEntityType.TEXT_LINK:
                    return entity.url
                if entity.type == MessageEntityType.URL:
                    return text_value[entity.offset:entity.offset + entity.length]
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
                duration = result.get("duration")
                vidid = result.get("id")
                thumbnail = result["thumbnails"][0]["url"].split("?")[0]
                seconds = time_to_seconds(duration) if duration else 0
                return result.get("title"), duration, seconds, thumbnail, vidid
        except Exception:
            pass
        try:
            options = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            }
            if os.path.exists("cookies.txt"):
                options["cookiefile"] = "cookies.txt"
            query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            result = await _async_run(
                yt_dlp.YoutubeDL(options).extract_info, query, download=False
            )
            entries = result.get("entries") if result else None
            entry = entries[0] if entries else result
            if entry:
                vidid = entry.get("id")
                seconds = int(entry.get("duration") or 0)
                minutes, secs = divmod(seconds, 60)
                hours, minutes = divmod(minutes, 60)
                duration = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
                return (
                    entry.get("title"), duration, seconds,
                    f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg", vidid
                )
        except Exception as error:
            LOGGER.error("details fallback error: %s", error)
        return None, None, None, None, None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            result = await VideosSearch(link, limit=1).next()
            return result["result"][0]["title"]
        except Exception:
            return "Unknown Title"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            result = await VideosSearch(link, limit=1).next()
            return result["result"][0]["duration"]
        except Exception:
            return "0:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            result = await VideosSearch(link, limit=1).next()
            return result["result"][0]["thumbnails"][0]["url"].split("?")[0]
        except Exception:
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
        except Exception as error:
            LOGGER.error("Video download error: %s", error)
            return 0, f"Video download error: {error}"

    async def playlist(
        self, link, limit, user_id, videoid: Union[bool, str] = None
    ):
        if videoid:
            link = self.listbase + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            playlist = await _async_run(Playlist.get, link)
            return [
                item["id"] for item in (playlist.get("videos") or [])[:limit]
                if item and item.get("id")
            ]
        except Exception as error:
            LOGGER.error("Playlist error: %s", error)
            return []

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            response = await VideosSearch(link, limit=1).next()
            if response and response.get("result"):
                result = response["result"][0]
                return {
                    "title": result.get("title"),
                    "link": result.get("link"),
                    "vidid": result.get("id"),
                    "duration_min": result.get("duration"),
                    "thumb": result["thumbnails"][0]["url"].split("?")[0],
                }, result.get("id")
        except Exception:
            pass
        try:
            options = {
                "quiet": True,
                "extract_flat": True,
                "noplaylist": True,
                "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            }
            if os.path.exists("cookies.txt"):
                options["cookiefile"] = "cookies.txt"
            query = link if "youtube.com" in link or "youtu.be" in link else f"ytsearch1:{link}"
            result = await _async_run(
                yt_dlp.YoutubeDL(options).extract_info, query, download=False
            )
            entries = result.get("entries") if result else None
            entry = entries[0] if entries else result
            if entry:
                vidid = entry.get("id")
                seconds = int(entry.get("duration") or 0)
                minutes, secs = divmod(seconds, 60)
                hours, minutes = divmod(minutes, 60)
                duration = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
                return {
                    "title": entry.get("title"),
                    "link": f"https://www.youtube.com/watch?v={vidid}",
                    "vidid": vidid,
                    "duration_min": duration,
                    "thumb": f"https://img.youtube.com/vi/{vidid}/hqdefault.jpg",
                }, vidid
        except Exception as error:
            LOGGER.error("track fallback error: %s", error)
        return None, None

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        options = {
            "quiet": True,
            "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
            "external_downloader": "aria2c",
            "external_downloader_args": ["-x", "16", "-s", "16", "-k", "1M"],
        }
        if os.path.exists("cookies.txt"):
            options["cookiefile"] = "cookies.txt"
        available = []
        try:
            result = await _async_run(
                yt_dlp.YoutubeDL(options).extract_info, link, download=False
            )
            for item in (result or {}).get("formats", []):
                if "dash" not in str(item.get("format", "")).lower():
                    available.append({
                        "format": item.get("format"),
                        "filesize": item.get("filesize"),
                        "format_id": item.get("format_id"),
                        "ext": item.get("ext"),
                        "format_note": item.get("format_note"),
                        "yturl": link,
                    })
        except Exception as error:
            LOGGER.error("Formats error: %s", error)
        return available, link

    async def slider(
        self, link: str, query_type: int, videoid: Union[bool, str] = None
    ):
        if videoid:
            link = self.base + link
        if "&" in link:
            link = link.split("&")[0]
        try:
            result = (await VideosSearch(link, limit=10).next()).get("result", [])
            item = result[query_type]
            return (
                item["title"], item.get("duration"),
                item["thumbnails"][0]["url"].split("?")[0], item["id"]
            )
        except Exception:
            return (
                "Unknown Title", "0:00",
                "https://telegra.ph/file/2e3d368e77c449c287430.jpg", "None"
            )

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None,
        videoid: Union[bool, str] = None, songaudio: Union[bool, str] = None,
        songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None,
        title: Union[bool, str] = None,
    ) -> str:
        if videoid:
            link = self.base + link
        try:
            file_title = title if isinstance(title, str) else None
            downloaded_file = (
                await download_video(link, title=file_title)
                if video else await download_song(link, title=file_title)
            )
            if downloaded_file:
                return downloaded_file, True
            return None, False
        except Exception as error:
            LOGGER.error("YouTubeAPI.download error: %s", error)
            return None, False

    async def autoplay(
        self, last_vidid: str, title: str, max_duration: int = None
    ):
        import random
        try:
            search_query = f"{title} official audio"
            choices = []
            try:
                response = await VideosSearch(search_query, limit=15).next()
                for item in (response or {}).get("result", []):
                    vidid = str(item.get("id") or "")
                    if not vidid or vidid == last_vidid:
                        continue
                    duration_text = str(item.get("duration") or "0:00")
                    duration_seconds = time_to_seconds(duration_text)
                    if duration_seconds < 30:
                        continue
                    if max_duration and duration_seconds > max_duration:
                        continue
                    choices.append({
                        "vidid": vidid,
                        "title": str(item.get("title") or "Unknown Title"),
                        "duration_min": duration_text,
                        "duration_sec": duration_seconds,
                    })
            except Exception as error:
                LOGGER.warning("Autoplay search fallback: %s", error)

            if not choices:
                options = {
                    "quiet": True,
                    "extract_flat": True,
                    "noplaylist": True,
                    "extractor_args": {"youtube": ["player_client=ios,tv_embedded"]},
                }
                if os.path.exists("cookies.txt"):
                    options["cookiefile"] = "cookies.txt"
                result = await _async_run(
                    yt_dlp.YoutubeDL(options).extract_info,
                    f"ytsearch10:{search_query}", download=False
                )
                for item in (result or {}).get("entries", []):
                    vidid = item.get("id")
                    if not vidid or vidid == last_vidid:
                        continue
                    try:
                        seconds = int(item.get("duration") or 0)
                    except (ValueError, TypeError):
                        continue
                    if seconds < 30 or (max_duration and seconds > max_duration):
                        continue
                    minutes, secs = divmod(seconds, 60)
                    hours, minutes = divmod(minutes, 60)
                    duration = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
                    choices.append({
                        "vidid": vidid,
                        "title": str(item.get("title") or "Unknown Title"),
                        "duration_min": duration,
                        "duration_sec": seconds,
                    })
            return random.choice(choices) if choices else None
        except Exception as error:
            LOGGER.error("YouTube autoplay error: %s", error)
            return None


YouTube = YouTubeAPI()
