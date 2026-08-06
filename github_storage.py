"""
GitHub 저장소를 데이터베이스처럼 사용하기 위한 헬퍼.
Streamlit Cloud는 재시작되면 로컬 파일이 사라지므로,
사진/정보를 전부 GitHub 저장소의 data/ 폴더에 커밋해서 영구 보관한다.
"""
import base64
import json
import requests
import streamlit as st

API_ROOT = "https://api.github.com"


def _cfg():
    s = st.secrets
    return {
        "token": s["GITHUB_TOKEN"],
        "repo": s["GITHUB_REPO"],           # 예: "myid/pet-memorial-data"
        "branch": s.get("GITHUB_BRANCH", "main"),
    }


def _headers():
    return {
        "Authorization": f"Bearer {_cfg()['token']}",
        "Accept": "application/vnd.github+json",
    }


def _url(path: str) -> str:
    repo = _cfg()["repo"]
    return f"{API_ROOT}/repos/{repo}/contents/{path}"


def get_file(path: str):
    """파일을 (bytes, sha) 로 반환. 없으면 None."""
    r = requests.get(_url(path), headers=_headers(), params={"ref": _cfg()["branch"]})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"])
    return content, data["sha"]


def list_dir(path: str):
    """디렉터리 안의 항목 목록. 없으면 빈 리스트."""
    r = requests.get(_url(path), headers=_headers(), params={"ref": _cfg()["branch"]})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return [data]
    return data


def put_file(path: str, content: bytes, message: str):
    """파일 생성 또는 수정(있으면 sha 자동 조회 후 덮어쓰기)."""
    existing = get_file(path)
    body = {
        "message": message,
        "content": base64.b64encode(content).decode("utf-8"),
        "branch": _cfg()["branch"],
    }
    if existing:
        body["sha"] = existing[1]
    r = requests.put(_url(path), headers=_headers(), data=json.dumps(body))
    r.raise_for_status()
    return r.json()


def delete_file(path: str, sha: str, message: str):
    body = {"message": message, "sha": sha, "branch": _cfg()["branch"]}
    r = requests.delete(_url(path), headers=_headers(), data=json.dumps(body))
    r.raise_for_status()
    return r.json()


def delete_folder(path: str, message: str):
    """폴더 안의 모든 파일을 재귀적으로 삭제."""
    items = list_dir(path)
    for item in items:
        if item["type"] == "dir":
            delete_folder(item["path"], message)
        else:
            delete_file(item["path"], item["sha"], message)


def get_json(path: str, default):
    got = get_file(path)
    if got is None:
        return default
    content, _ = got
    return json.loads(content.decode("utf-8"))


def put_json(path: str, obj, message: str):
    content = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    put_file(path, content, message)
