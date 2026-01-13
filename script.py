import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

YOUTUBE_ROOT = "https://www.youtube.com"


def _extract_innertube(html: str) -> Tuple[str, str]:
    """
    Extrai INNERTUBE_API_KEY e INNERTUBE_CLIENT_VERSION do HTML.
    """
    api_key_m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    ver_m = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html)
    if not api_key_m or not ver_m:
        raise RuntimeError("Não foi possível extrair INNERTUBE_API_KEY / INNERTUBE_CLIENT_VERSION do HTML.")
    return api_key_m.group(1), ver_m.group(1)


def _extract_ytinitialdata(html: str) -> Dict[str, Any]:
    """
    Extrai o ytInitialData do HTML.
    """
    m = re.search(r"var\s+ytInitialData\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
    if not m:
        m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
    if not m:
        raise RuntimeError("Não foi possível extrair ytInitialData do HTML.")
    return json.loads(m.group(1))


def _walk(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk(it)


def _pick_text(t: Any) -> str:
    if not isinstance(t, dict):
        return ""
    if "simpleText" in t and isinstance(t["simpleText"], str):
        return t["simpleText"]
    if "runs" in t and isinstance(t["runs"], list):
        return "".join(r.get("text", "") for r in t["runs"] if isinstance(r, dict))
    return ""


def _parse_video_renderer(vr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    vid = vr.get("videoId")
    if not vid:
        return None

    title = _pick_text(vr.get("title", {}))

    # Snippet pode vir truncado (descrição completa pode ser buscada depois)
    desc = ""
    if isinstance(vr.get("descriptionSnippet"), dict):
        desc = _pick_text(vr["descriptionSnippet"])
    elif isinstance(vr.get("detailedMetadataSnippets"), list) and vr["detailedMetadataSnippets"]:
        snippet = vr["detailedMetadataSnippets"][0].get("snippetText", {})
        desc = _pick_text(snippet)

    thumb = ""
    thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
    if isinstance(thumbs, list) and thumbs:
        thumb = thumbs[-1].get("url", "") or ""

    return {
        "videoId": vid,
        "url": f"{YOUTUBE_ROOT}/watch?v={vid}",
        "title": title,
        "description": desc,
        "thumbnail": thumb,
    }


def _extract_videos_and_continuation(data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Extrai vídeos e token de continuação (se existir) do payload (ytInitialData ou browse response).
    """
    videos: List[Dict[str, Any]] = []
    continuation: Optional[str] = None

    # Vídeos aparecem como gridVideoRenderer ou videoRenderer dependendo do layout
    for k, v in _walk(data):
        if k in ("gridVideoRenderer", "videoRenderer") and isinstance(v, dict):
            parsed = _parse_video_renderer(v)
            if parsed:
                videos.append(parsed)

    # Continuação geralmente aparece como continuationItemRenderer -> continuationEndpoint -> continuationCommand -> token
    for k, v in _walk(data):
        if k == "continuationItemRenderer" and isinstance(v, dict):
            token = (
                v.get("continuationEndpoint", {})
                 .get("continuationCommand", {})
                 .get("token")
            )
            if token:
                continuation = token
                break

    # Fallback: algumas respostas trazem token em continuationCommand diretamente
    if not continuation:
        for k, v in _walk(data):
            if k == "continuationCommand" and isinstance(v, dict) and v.get("token"):
                continuation = v["token"]
                break

    return videos, continuation


def _browse_continuation(
    session: requests.Session,
    api_key: str,
    client_version: str,
    continuation: str,
    referer: str,
    sleep_s: float = 0.15,
) -> Dict[str, Any]:
    """
    Chama o endpoint interno do YouTube para paginar resultados.
    Endpoint é sempre na raiz: https://www.youtube.com/youtubei/v1/browse
    """
    url = f"{YOUTUBE_ROOT}/youtubei/v1/browse?key={api_key}"

    headers = {
        "Content-Type": "application/json",
        "Origin": YOUTUBE_ROOT,
        "Referer": referer,
        "X-Youtube-Client-Name": "1",  # WEB
        "X-Youtube-Client-Version": client_version,
    }

    payload = {
        "context": {
            "client": {
                "hl": "pt-BR",
                "gl": "BR",
                "clientName": "WEB",
                "clientVersion": client_version,
            }
        },
        "continuation": continuation,
    }

    resp = session.post(url, headers=headers, json=payload, timeout=30)

    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} no browse. Body (parcial): {resp.text[:500]}")

    data = resp.json()

    if sleep_s:
        time.sleep(sleep_s)

    return data


def _fetch_full_description(session: requests.Session, video_url: str) -> str:
    """
    Abre a página do vídeo e extrai descrição completa do ytInitialPlayerResponse.videoDetails.shortDescription
    """
    r = session.get(video_url, timeout=30)
    r.raise_for_status()
    html = r.text

    m = re.search(r"var\s+ytInitialPlayerResponse\s*=\s*(\{.*?\});", html, flags=re.DOTALL)
    if not m:
        return ""

    try:
        player = json.loads(m.group(1))
    except json.JSONDecodeError:
        return ""

    return (player.get("videoDetails", {}) or {}).get("shortDescription", "") or ""


def get_all_channel_videos(
    channel_url: str,
    fetch_full_description: bool = True,
    max_videos: Optional[int] = None,
    output_filename: str = "youtube_videos.json",
) -> str:
    """
    Coleta todos os vídeos do canal e salva em JSON no mesmo diretório do script.
    Exibe progresso em % durante a coleta de descrições (fase 2).

    Returns:
      Caminho absoluto do arquivo JSON salvo.
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
    )

    videos_url = channel_url.rstrip("/") + "/videos"

    print("[1/2] Carregando página do canal...")
    r = session.get(videos_url, timeout=30)
    r.raise_for_status()
    html = r.text

    api_key, client_version = _extract_innertube(html)
    initial = _extract_ytinitialdata(html)

    videos: List[Dict[str, Any]] = []
    seen = set()
    page_count = 0

    page_videos, continuation = _extract_videos_and_continuation(initial)
    page_count += 1

    for v in page_videos:
        if v["videoId"] not in seen:
            seen.add(v["videoId"])
            videos.append(v)

    print(f"[1/2] Coletando lista de vídeos... páginas: {page_count} | vídeos: {len(videos)}")

    while continuation and (not max_videos or len(videos) < max_videos):
        data = _browse_continuation(
            session=session,
            api_key=api_key,
            client_version=client_version,
            continuation=continuation,
            referer=videos_url,
        )

        page_videos, new_cont = _extract_videos_and_continuation(data)
        page_count += 1

        for v in page_videos:
            if v["videoId"] not in seen:
                seen.add(v["videoId"])
                videos.append(v)
                if max_videos and len(videos) >= max_videos:
                    break

        print(f"[1/2] Coletando lista de vídeos... páginas: {page_count} | vídeos: {len(videos)}")

        if not new_cont or new_cont == continuation:
            break
        continuation = new_cont

    if max_videos:
        videos = videos[:max_videos]

    total_videos = len(videos)

    # Fase 2: descrição completa (progresso em %)
    if fetch_full_description and total_videos > 0:
        print("[2/2] Buscando descrições completas dos vídeos...")
        for idx, video in enumerate(videos, start=1):
            try:
                video["description"] = _fetch_full_description(session, video["url"])
            except Exception:
                pass

            percent = int((idx / total_videos) * 100)
            print(f"[2/2] Progresso: {percent}% ({idx}/{total_videos})", end="\r", flush=True)
            time.sleep(0.12)

        print("\n[2/2] Descrições finalizadas.")

    result = {
        "channel": channel_url,
        "videos_tab": videos_url,
        "count": total_videos,
        "videos": [
            {
                "url": v["url"],
                "title": v["title"],
                "description": v["description"],
                "thumbnail": v["thumbnail"],
            }
            for v in videos
        ],
    }

    # Salvar no mesmo diretório do script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(base_dir, output_filename)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[OK] JSON salvo em: {output_path}")

    return output_path


if __name__ == "__main__":
    channel = "https://www.youtube.com/@NicoChat"

    # fetch_full_description=True => mais lento, mas descrição completa
    # fetch_full_description=False => mais rápido, mas descrição pode vir truncada
    get_all_channel_videos(
        channel_url=channel,
        fetch_full_description=True,
        output_filename="youtube_videos.json",
    )
