import io
import uuid
import datetime as dt

import streamlit as st
from PIL import Image, ImageOps

import github_storage as gh
from backup_utils import build_pet_zip, make_downloadable_backup

st.set_page_config(page_title="우리 아이들", page_icon="🐾", layout="centered")

PETS_PATH = "data/pets.json"
MAX_DIMENSION = 1600  # 긴 변 기준 최대 픽셀 (모바일 화면에 충분한 크기)
JPEG_QUALITY = 85


def resize_image(raw_bytes: bytes) -> tuple[bytes, str]:
    """업로드된 이미지를 모바일 보기에 적당한 크기로 리사이즈하고 JPEG로 압축.
    반환값: (압축된 bytes, 파일 확장자 'jpg')"""
    img = Image.open(io.BytesIO(raw_bytes))
    img = ImageOps.exif_transpose(img)  # 휴대폰 사진 회전 정보 보정
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > MAX_DIMENSION:
        ratio = MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), "jpg"


# ---------- 데이터 로드/저장 ----------

def load_pets():
    return gh.get_json(PETS_PATH, default=[])


def save_pets(pets):
    gh.put_json(PETS_PATH, pets, message="update pets.json")


def load_gallery(pet_id):
    return gh.get_json(f"data/{pet_id}/gallery.json", default=[])


def save_gallery(pet_id, gallery):
    gh.put_json(f"data/{pet_id}/gallery.json", gallery, message=f"update gallery for {pet_id}")


def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- 홈 탭 ----------

def render_home(pets):
    st.subheader("🏠 최신 소식")
    if not pets:
        st.info("아직 등록된 아이가 없어요. '➕ 추가' 탭에서 등록해 주세요.")
        return

    events = []
    for pet in pets:
        gallery = load_gallery(pet["id"])
        for item in gallery:
            events.append({
                "type": "photo",
                "pet_name": pet["name"],
                "pet_id": pet["id"],
                "filename": item["filename"],
                "time": item["uploaded_at"],
                "text": None,
            })
            for c in item.get("comments", []):
                events.append({
                    "type": "comment",
                    "pet_name": pet["name"],
                    "pet_id": pet["id"],
                    "filename": item["filename"],
                    "time": c["timestamp"],
                    "text": c["text"],
                })

    events.sort(key=lambda e: e["time"], reverse=True)

    if not events:
        st.info("아직 사진이나 댓글이 없어요.")
        return

    for e in events[:10]:
        got = gh.get_file(f"data/{e['pet_id']}/photos/{e['filename']}")
        cols = st.columns([1, 2])
        with cols[0]:
            if got:
                st.image(got[0], use_container_width=True)
        with cols[1]:
            st.caption(f"{e['time']} · {e['pet_name']}")
            if e["type"] == "comment":
                st.write(f"💬 {e['text']}")
            else:
                st.write("📷 새 사진이 올라왔어요")
        st.divider()


# ---------- 반려동물 탭 ----------

def render_pet_tab(pet, pets):
    pet_id = pet["id"]

    with st.expander("📋 프로필 보기 / 수정", expanded=False):
        with st.form(f"info_form_{pet_id}"):
            species = st.text_input("종류(예: 고양이/강아지)", value=pet.get("species", ""))
            birth = st.text_input("생년월일 (예: 2015-03-01)", value=pet.get("birth_date", ""))
            death = st.text_input("사망년월일 (없으면 비워두세요)", value=pet.get("death_date", ""))
            food = st.text_input("좋아했던 음식", value=pet.get("favorite_food", ""))
            trait = st.text_area("특징", value=pet.get("characteristics", ""))
            submitted = st.form_submit_button("저장")
            if submitted:
                pet.update({
                    "species": species,
                    "birth_date": birth,
                    "death_date": death,
                    "favorite_food": food,
                    "characteristics": trait,
                })
                save_pets(pets)
                st.success("저장했어요.")
                st.rerun()

        st.markdown("---")
        confirm = st.checkbox(f"'{pet['name']}' 삭제를 확인합니다 (사진/댓글 전부 삭제됨)", key=f"del_confirm_{pet_id}")
        if st.button("🗑️ 이 아이 삭제하기", key=f"del_btn_{pet_id}", disabled=not confirm):
            gh.delete_folder(f"data/{pet_id}", message=f"delete pet {pet_id}")
            pets[:] = [p for p in pets if p["id"] != pet_id]
            save_pets(pets)
            st.success("삭제했어요.")
            st.rerun()

    st.markdown("#### 📸 사진 올리기")
    uploaded = st.file_uploader("사진 선택", type=["jpg", "jpeg", "png", "webp"], key=f"upl_{pet_id}")
    if uploaded is not None:
        if st.button("업로드", key=f"upl_btn_{pet_id}"):
            with st.spinner("사진 크기 조정 중..."):
                resized_bytes, ext = resize_image(uploaded.getvalue())
            filename = f"{uuid.uuid4().hex[:8]}.{ext}"
            gh.put_file(f"data/{pet_id}/photos/{filename}", resized_bytes,
                        message=f"add photo for {pet_id}")
            gallery = load_gallery(pet_id)
            gallery.append({
                "filename": filename,
                "uploaded_at": now_str(),
                "comments": [],
            })
            save_gallery(pet_id, gallery)
            st.success("업로드 완료!")
            st.rerun()

    st.markdown("#### 🖼️ 갤러리")
    gallery = load_gallery(pet_id)
    gallery_sorted = sorted(gallery, key=lambda g: g["uploaded_at"], reverse=True)

    if not gallery_sorted:
        st.caption("아직 사진이 없어요.")

    for item in gallery_sorted:
        got = gh.get_file(f"data/{pet_id}/photos/{item['filename']}")
        if got:
            st.image(got[0], use_container_width=True)
        st.caption(item["uploaded_at"])

        for c in item.get("comments", []):
            st.write(f"💬 {c['text']}  ·  _{c['timestamp']}_")

        new_comment = st.text_input("댓글 달기", key=f"comment_{pet_id}_{item['filename']}")
        if st.button("댓글 등록", key=f"comment_btn_{pet_id}_{item['filename']}"):
            if new_comment.strip():
                item.setdefault("comments", []).append({
                    "text": new_comment.strip(),
                    "timestamp": now_str(),
                })
                save_gallery(pet_id, gallery)
                st.success("댓글을 남겼어요.")
                st.rerun()
        st.divider()

    st.markdown("#### 💾 백업")
    chunk_mb = st.number_input("분할 기준 용량(MB) — 이보다 크면 자동으로 나눠요",
                                min_value=5, max_value=100, value=20, step=5, key=f"chunk_{pet_id}")
    if st.button("백업 파일 만들기", key=f"backup_btn_{pet_id}"):
        with st.spinner("압축하는 중..."):
            photos = {}
            for item in gallery:
                got = gh.get_file(f"data/{pet_id}/photos/{item['filename']}")
                if got:
                    photos[item["filename"]] = got[0]
            zip_bytes = build_pet_zip(pet, gallery, photos)
            data, split, fname = make_downloadable_backup(pet_id, zip_bytes, chunk_mb)
        st.session_state[f"backup_ready_{pet_id}"] = (data, fname, split)

    ready = st.session_state.get(f"backup_ready_{pet_id}")
    if ready:
        data, fname, split = ready
        size_mb = len(data) / (1024 * 1024)
        if split:
            st.caption(f"용량이 커서 여러 조각으로 나눴어요. (다운로드 파일 크기 약 {size_mb:.1f}MB, 안에 merge.py 포함)")
        else:
            st.caption(f"압축 완료 (약 {size_mb:.1f}MB)")
        st.download_button("⬇️ 백업 다운로드", data=data, file_name=fname, key=f"dl_{pet_id}")


# ---------- 추가 탭 ----------

def render_add_tab(pets):
    st.subheader("➕ 새로운 아이 등록")
    with st.form("add_pet_form"):
        name = st.text_input("이름")
        species = st.text_input("종류(예: 고양이/강아지)")
        birth = st.text_input("생년월일 (예: 2015-03-01)")
        death = st.text_input("사망년월일 (없으면 비워두세요)")
        food = st.text_input("좋아했던 음식")
        trait = st.text_area("특징")
        submitted = st.form_submit_button("등록")
        if submitted:
            if not name.strip():
                st.error("이름을 입력해 주세요.")
            else:
                new_pet = {
                    "id": uuid.uuid4().hex[:10],
                    "name": name.strip(),
                    "species": species,
                    "birth_date": birth,
                    "death_date": death,
                    "favorite_food": food,
                    "characteristics": trait,
                }
                pets.append(new_pet)
                save_pets(pets)
                st.success(f"{name} 등록 완료!")
                st.rerun()


# ---------- 메인 ----------

def main():
    st.title("🐾 우리 아이들")

    try:
        pets = load_pets()
    except Exception as e:
        st.error("GitHub 저장소 연결에 실패했어요. secrets 설정을 확인해 주세요.")
        st.exception(e)
        return

    tab_labels = ["🏠 홈"] + [p["name"] for p in pets] + ["➕ 추가"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        render_home(pets)

    for i, pet in enumerate(pets, start=1):
        with tabs[i]:
            render_pet_tab(pet, pets)

    with tabs[-1]:
        render_add_tab(pets)


if __name__ == "__main__":
    main()
