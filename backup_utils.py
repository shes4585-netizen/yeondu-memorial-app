"""
반려동물 한 마리 분량의 데이터를 최대 압축률로 zip 압축하고,
용량이 크면 여러 조각으로 나눠서 하나의 다운로드 파일(컨테이너)에 담는다.
"""
import io
import json
import zipfile

MERGE_SCRIPT = '''\
# merge.py
# 이 폴더에서 실행하면 분할된 조각들을 합쳐서 원래 zip 파일을 복원합니다.
# 사용법: python merge.py
import glob

parts = sorted(glob.glob("*_backup.zip.*"))
if not parts:
    print("합칠 조각 파일을 찾지 못했습니다.")
else:
    out_name = parts[0].rsplit(".", 1)[0]  # "xxx_backup.zip"
    with open(out_name, "wb") as out:
        for p in parts:
            with open(p, "rb") as f:
                out.write(f.read())
    print(f"복원 완료: {out_name}")
'''

INSTRUCTIONS_KO = """\
[백업 복원 방법]

1. 이 안의 *_backup.zip.001, .002 ... 파일들과 merge.py를 같은 폴더에 둡니다.
2. 터미널(명령 프롬프트)에서 python merge.py 를 실행합니다.
3. 원래의 압축 zip 파일이 만들어지며, 그 안에 사진과 정보가 들어 있습니다.

(용량이 작아 분할되지 않은 경우 이 안내문은 필요 없습니다.)
"""


def build_pet_zip(pet_info: dict, gallery: list, photos: dict) -> bytes:
    """photos: {filename: bytes}"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("info.json", json.dumps(pet_info, ensure_ascii=False, indent=2))
        zf.writestr("gallery.json", json.dumps(gallery, ensure_ascii=False, indent=2))
        for filename, content in photos.items():
            zf.writestr(f"photos/{filename}", content)
    return buf.getvalue()


def make_downloadable_backup(pet_id: str, zip_bytes: bytes, chunk_size_mb: int = 20):
    """
    chunk_size_mb 기준으로 넘으면 여러 조각으로 나눠 하나의 컨테이너 zip으로 묶는다.
    반환값: (다운로드용 bytes, 분할여부, 최종 파일명)
    """
    chunk_size = chunk_size_mb * 1024 * 1024
    if len(zip_bytes) <= chunk_size:
        return zip_bytes, False, f"{pet_id}_backup.zip"

    parts = [zip_bytes[i:i + chunk_size] for i in range(0, len(zip_bytes), chunk_size)]
    container = io.BytesIO()
    with zipfile.ZipFile(container, "w", zipfile.ZIP_STORED) as zf:
        for idx, part in enumerate(parts, 1):
            zf.writestr(f"{pet_id}_backup.zip.{idx:03d}", part)
        zf.writestr("merge.py", MERGE_SCRIPT)
        zf.writestr("사용법.txt", INSTRUCTIONS_KO)
    return container.getvalue(), True, f"{pet_id}_backup_split_{len(parts)}parts.zip"
