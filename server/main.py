import os, json, pathlib
from typing import Any, Literal, Optional
import asyncio
import httpx
try:
    import keyring  # 선택이지만 권장
except Exception:  # keyring이 없더라도 동작하도록
    keyring = None  # type: ignore

from mcp.server.fastmcp import FastMCP, Context

STDICT_SEARCH_URL = "https://stdict.korean.go.kr/api/search.do"
STDICT_VIEW_URL = "https://stdict.korean.go.kr/api/view.do"
USER_AGENT = "ko-stdict-mcp-server/1.0"
CONFIG_PATH = pathlib.Path.home() / ".stdict_mcp" / "config.json"
ENV_KEY_NAME = "STDICT_API_KEY"
KEYRING_SERVICE = "stdict_mcp"
KEYRING_USERNAME = "api_key"

mcp = FastMCP("stdict")

# 정적 리소스 추가 (List Resources 오류 방지용)
@mcp.resource("stdict://help")
async def help_resource() -> tuple[str, bytes]:
    """표준국어대사전 MCP 서버 사용법"""
    content = """# 표준국어대사전 MCP 서버

## 사용법

### 1. 검색
search(q="검색어")

### 2. 단어 상세 조회 (JSON)
entry(target_code=숫자)

### 3. 단어 상세 조회 (마크다운)
리소스 URI: stdict://entry/{target_code}

## 예시
1. search(q="사랑") - 사랑 관련 단어들 검색
2. entry(target_code=435977) - 특정 단어의 상세 정보 (JSON)
3. 리소스에서 stdict://entry/435977 - 특정 단어의 상세 정보 (마크다운)
"""
    return ("text/markdown", content.encode("utf-8"))

async def get_api_key(ctx: Optional[Context] = None) -> str:
    # 1) env
    if os.getenv(ENV_KEY_NAME):
        return os.environ[ENV_KEY_NAME]

    # 2) config file
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            k = data.get("api_key")
            if k:
                return k
    except Exception:
        pass

    # 3) keyring
    if keyring is not None:
        try:
            k = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
            if k:
                return k
        except Exception:
            pass

    # 4) elicitation (클라이언트가 지원해야 함)
    if ctx is not None:
        result = await ctx.elicit(
            message="국립국어원 표준국어대사전 Open API 인증키를 입력해 주세요.",
            response_type=str,
        )
        if getattr(result, "action", None) == "accept" and getattr(result, "data", None):
            api_key = str(result.data).strip()
            # keyring 저장 시도
            try:
                if keyring is not None:
                    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
            except Exception:
                pass
            # config 파일 저장(폴백)
            try:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                CONFIG_PATH.write_text(json.dumps({"api_key": api_key}, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            return api_key

    raise RuntimeError("API 키가 필요합니다. 환경변수 STDICT_API_KEY 또는 설정에 키를 등록해 주세요.")

async def request_json(url: str, params: dict[str, Any]) -> dict:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
        r = await client.get(url, params=params, headers=headers)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            # 응답이 JSON이 아닐 때, 앞부분만 잘라 보여주기
            snippet = r.text[:500]
            raise RuntimeError(f"예상치 못한 응답 형식(최초 500자): {snippet}")

def humanize_error(err_json: dict[str, Any]) -> str:
    err = err_json.get("error", {})
    code = str(err.get("error_code", ""))
    msg  = err.get("message", "")
    known = {
        "020": "등록되지 않은 키입니다.",
        "021": "일시적으로 사용 중지된 인증 키입니다.",
        "100": "부적절한 쿼리 요청입니다(q 누락 등).",
        "103": "부적절한 검색 개수(num)입니다.",
    }
    base = known.get(code, "요청 중 오류가 발생했습니다.")
    return f"[{code}] {base}{(' - ' + msg) if msg else ''}"

async def _fetch_entry_by_target_code(target_code: int, ctx: Optional[Context] = None) -> dict:
    key = await get_api_key(ctx)
    params = {
        "key": key,
        "type_search": "view",
        "req_type": "json",
        "method": "TARGET_CODE",
        "q": str(target_code),
    }
    raw = await request_json(STDICT_VIEW_URL, params)
    if "error" in raw:
        raise RuntimeError(humanize_error(raw))

    ch = (raw.get("channel") or {})
    item = (ch.get("item") or {})
    wi = (item.get("word_info") or {})
    word = wi.get("word")
    pos = ""
    senses = []

    # pos_info가 리스트/단일 모두 허용
    pi_list = wi.get("pos_info", [])
    if not isinstance(pi_list, list):
        pi_list = [pi_list] if pi_list else []

    for pi in pi_list:
        if not isinstance(pi, dict):
            continue
        if not pos:
            pos = pi.get("pos", "")  # 첫 품사만 사용

        # comm_pattern_info가 리스트/단일 모두 허용
        cpi_list = pi.get("comm_pattern_info", [])
        if not isinstance(cpi_list, list):
            cpi_list = [cpi_list] if cpi_list else []

        for cpi in cpi_list:
            if not isinstance(cpi, dict):
                continue
            si_list = cpi.get("sense_info", [])
            if not isinstance(si_list, list):
                si_list = [si_list] if si_list else []

            for sense in si_list:
                if not isinstance(sense, dict):
                    continue
                exs = []
                exi = sense.get("example_info")
                if isinstance(exi, list):
                    for e in exi:
                        if isinstance(e, dict) and e.get("example"):
                            exs.append(e["example"])
                elif isinstance(exi, dict) and exi.get("example"):
                    exs.append(exi["example"])

                senses.append({
                    "type": sense.get("type"),
                    "definition": sense.get("definition"),
                    "examples": exs,
                })

    return {
        "target_code": int(target_code),
        "word": word,
        "pos": pos,
        "senses": senses,
    }


@mcp.resource("stdict://entry/{target_code}")
async def entry_resource(target_code: int) -> tuple[str, bytes]:
    """표준국어대사전 단어 항목을 마크다운으로 제공"""
    data = await _fetch_entry_by_target_code(int(target_code))
    
    # 마크다운 렌더링
    lines = [
        f"# {data.get('word','')} ({data.get('pos','')})",
        f"*target_code*: {target_code}",
        ""
    ]
    for i, s in enumerate(data.get("senses", []), 1):
        t = s.get("type") or ""
        d = s.get("definition") or ""
        lines.append(f"## 뜻 {i}. {t}")
        lines.append(d)
        exs = s.get("examples") or []
        if exs:
            lines.append("")
            lines.append("**용례**")
            lines.extend([f"- {e}" for e in exs])
        lines.append("")
    
    md = "\n".join(lines).encode("utf-8")
    return ("text/markdown", md)

# 도구 1: 검색 (여러 결과)
@mcp.tool("stdict_search")
async def search(ctx: Context, q: str, start: int = 1, num: int = 10,
                 advanced: Literal["n","y"] = "n") -> dict:
    """
    표준국어대사전을 검색합니다.
    Returns: { total, start, num, items: [{target_code, word, pos, definition, link, type}] }
    """
    # 파라미터 검증
    if start < 1:
        start = 1
    if num < 10:
        num = 10
    elif num > 100:
        num = 100

    key = await get_api_key(ctx)
    params = {
        "key": key,
        "type_search": "search",
        "q": q,
        "req_type": "json",
        "start": start,
        "num": num,
        "advanced": advanced,
    }
    data = await request_json(STDICT_SEARCH_URL, params)
    if "error" in data:
        raise RuntimeError(humanize_error(data))

    ch = data.get("channel", {})
    items = []

    items_raw = ch.get("item") or []
    if isinstance(items_raw, dict):  # 단일 객체 방어
        items_raw = [items_raw]

    for it in items_raw:
        sense = it.get("sense") or {}
        target_code = it.get("target_code")
        items.append({
            "target_code": target_code,
            "word": it.get("word"),
            "pos": it.get("pos"),
            "definition": sense.get("definition"),
            "link": sense.get("link"),
            "type": sense.get("type"),
            "resource_uri": f"stdict://entry/{target_code}",  # 리소스 URI 힌트
        })

    return {
        "total": ch.get("total", 0),
        "start": ch.get("start", start),
        "num": ch.get("num", num),
        "items": items,
    }

# 도구 2: 단일 항목 조회 (JSON 형태, 체인/가공용)
@mcp.tool("stdict_entry")
async def entry(ctx: Context, target_code: int) -> dict:
    """
    target_code로 표준국어대사전 단어 항목을 JSON으로 가져옵니다.
    체인 처리나 데이터 가공에 적합합니다.
    
    마크다운으로 읽기 좋게 보려면 리소스를 사용하세요: stdict://entry/{target_code}
    """
    result = await _fetch_entry_by_target_code(int(target_code), ctx)
    # 리소스 URI 힌트 추가
    result["resource_uri"] = f"stdict://entry/{target_code}"
    return result

if __name__ == "__main__":
    mcp.run(transport="stdio")
