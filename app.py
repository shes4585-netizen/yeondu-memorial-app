import io
import time
import uuid
import datetime as dt

import streamlit as st
from PIL import Image, ImageOps

import github_storage as gh
from intro_audio import INTRO_AUDIO_B64
from door_image import DOOR_IMAGE_B64
from backup_utils import build_pet_zip, make_downloadable_backup

st.set_page_config(page_title="꼬리별", page_icon="🐾", layout="centered")

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
# GitHub API는 커밋 직후 바로 다시 읽으면 잠깐 예전 값이 보일 수 있어서,
# 세션 안에서는 방금 저장한 값을 그대로 기억해뒀다가 돌려준다.

def load_pets():
    if "_pets_cache" not in st.session_state:
        st.session_state["_pets_cache"] = gh.get_json(PETS_PATH, default=[])
    return st.session_state["_pets_cache"]


def save_pets(pets):
    gh.put_json(PETS_PATH, pets, message="update pets.json")
    st.session_state["_pets_cache"] = pets


def load_gallery(pet_id):
    cache = st.session_state.setdefault("_gallery_cache", {})
    if pet_id not in cache:
        cache[pet_id] = gh.get_json(f"data/{pet_id}/gallery.json", default=[])
    return cache[pet_id]


def save_gallery(pet_id, gallery):
    gh.put_json(f"data/{pet_id}/gallery.json", gallery, message=f"update gallery for {pet_id}")
    st.session_state.setdefault("_gallery_cache", {})[pet_id] = gallery


KST = dt.timezone(dt.timedelta(hours=9))


def now_str():
    return dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


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
            comments = item.get("comments", [])
            if comments:
                latest_comment = max(comments, key=lambda c: c["timestamp"])
                latest_time = latest_comment["timestamp"]
                event_type = "comment"
                text = latest_comment["text"]
            else:
                latest_time = item["uploaded_at"]
                event_type = "photo"
                text = None

            events.append({
                "type": event_type,
                "pet_name": pet["name"],
                "pet_id": pet["id"],
                "filename": item["filename"],
                "time": latest_time,
                "text": text,
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
            st.session_state.setdefault("_gallery_cache", {}).pop(pet_id, None)
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

        for idx, c in enumerate(item.get("comments", [])):
            edit_key = f"editing_{pet_id}_{item['filename']}_{idx}"
            if st.session_state.get(edit_key, False):
                edited_text = st.text_input(
                    "댓글 수정", value=c["text"],
                    key=f"edit_input_{pet_id}_{item['filename']}_{idx}",
                )
                ec1, ec2 = st.columns(2)
                with ec1:
                    if st.button("저장", key=f"edit_save_{pet_id}_{item['filename']}_{idx}"):
                        if edited_text.strip():
                            c["text"] = edited_text.strip()
                            c["timestamp"] = now_str()
                            save_gallery(pet_id, gallery)
                            st.session_state[edit_key] = False
                            st.success("댓글을 수정했어요.")
                            st.rerun()
                with ec2:
                    if st.button("취소", key=f"edit_cancel_{pet_id}_{item['filename']}_{idx}"):
                        st.session_state[edit_key] = False
                        st.rerun()
            else:
                st.write(f"💬 {c['text']}  ·  _{c['timestamp']}_")
                ecol1, ecol2, _rest = st.columns([1, 1, 4])
                with ecol1:
                    if st.button("✏️", key=f"edit_btn_{pet_id}_{item['filename']}_{idx}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                with ecol2:
                    if st.button("🗑️", key=f"cdel_btn_{pet_id}_{item['filename']}_{idx}"):
                        item["comments"].pop(idx)
                        save_gallery(pet_id, gallery)
                        st.success("댓글을 삭제했어요.")
                        st.rerun()

        new_comment = st.text_input(
            "댓글 달기",
            key=f"comment_{pet_id}_{item['filename']}",
            placeholder="여기 클릭 후 입력해 주세요",
        )
        if st.button("댓글 등록", key=f"comment_btn_{pet_id}_{item['filename']}"):
            if new_comment.strip():
                item.setdefault("comments", []).append({
                    "text": new_comment.strip(),
                    "timestamp": now_str(),
                })
                save_gallery(pet_id, gallery)
                st.success("댓글을 남겼어요.")
                st.rerun()

        del_col1, del_col2 = st.columns([3, 1])
        with del_col1:
            del_confirm = st.checkbox("이 사진 삭제 확인", key=f"delc_{pet_id}_{item['filename']}")
        with del_col2:
            if st.button("🗑️ 삭제", key=f"delbtn_{pet_id}_{item['filename']}", disabled=not del_confirm):
                if got:
                    gh.delete_file(f"data/{pet_id}/photos/{item['filename']}", got[1],
                                    message=f"delete photo {item['filename']}")
                gallery[:] = [g for g in gallery if g["filename"] != item["filename"]]
                save_gallery(pet_id, gallery)
                st.success("사진을 삭제했어요.")
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

def show_entrance_animation():
    """하늘의 문이 열리며 '우리 아이를 보러 갑니다' 문구가 하늘로 사라지는 20초 인트로."""
    stars = ""
    star_positions = [
        (6, 8, 3), (14, 22, 2), (22, 6, 4), (30, 30, 2), (38, 12, 3),
        (46, 26, 2), (54, 9, 4), (62, 20, 2), (70, 5, 3), (78, 28, 2),
        (86, 14, 4), (10, 34, 2), (18, 40, 3), (44, 38, 2), (60, 36, 3),
        (76, 40, 2), (90, 32, 3), (4, 20, 2), (94, 18, 2), (50, 4, 2),
    ]
    for left, top, size in star_positions:
        delay = (left % 10) / 10 * 3
        stars += (
            f'<div style="position:absolute; left:{left}%; top:{top}%; '
            f'width:{size}px; height:{size}px; background:#fff; border-radius:50%; '
            f'box-shadow:0 0 6px 1px rgba(255,255,255,0.8); '
            f'opacity:.3; animation: twinkle 2.4s ease-in-out {delay}s infinite;"></div>'
        )

    # 떠난 아이들을 상징하는 큰 별 (더 밝고 크게 반짝임)
    big_star_positions = [(16, 14, 9), (58, 8, 10), (34, 24, 8), (82, 20, 9)]
    for left, top, size in big_star_positions:
        delay = (left % 10) / 10 * 2.5
        stars += (
            f'<div style="position:absolute; left:{left}%; top:{top}%; '
            f'width:{size}px; height:{size}px; background:#fff3c4; border-radius:50%; '
            f'box-shadow:0 0 16px 5px rgba(255,243,196,0.9); '
            f'opacity:.5; animation: big-twinkle 3.2s ease-in-out {delay}s infinite;"></div>'
        )

    html = f"""
    <audio id="introAudio" autoplay>
      <source src="data:audio/mp4;base64,{INTRO_AUDIO_B64}" type="audio/mp4">
    </audio>
    <div style="
        position:relative; width:100%; height:340px; overflow:hidden; border-radius:12px;
        background: linear-gradient(180deg, #05081a 0%, #10204a 30%, #3a5a8c 55%, #a8c9e8 78%, #fdf3d9 100%);
        animation: overlay-fade-out 2s ease-in 18s forwards;">

      {stars}

      <!-- 문 너머로 보이는 빛 -->
      <div style="
          position:absolute; left:50%; top:50%; width:280px; height:280px;
          transform: translate(-50%,-50%); border-radius:50%;
          background: radial-gradient(circle, rgba(255,244,214,0.95) 0%, rgba(255,244,214,0.35) 45%, rgba(255,244,214,0) 75%);
          opacity:0; animation: glow-in 20s ease-in forwards;">
      </div>

      <!-- 왼쪽 문 -->
      <div style="
          position:absolute; top:0; left:0; width:50%; height:100%;
          background-image:
            linear-gradient(rgba(0,0,0,0.10), rgba(0,0,0,0.10)),
            url('data:image/jpeg;base64,{DOOR_IMAGE_B64}');
          background-size: 100% 100%, 200% 100%;
          background-position: center, left center;
          border-right: 3px solid #8a6f43;
          box-shadow: 8px 0 18px rgba(0,0,0,0.35);
          animation: open-left 14s ease-in-out 1s forwards;">
      </div>

      <!-- 오른쪽 문 -->
      <div style="
          position:absolute; top:0; right:0; width:50%; height:100%;
          background-image:
            linear-gradient(rgba(0,0,0,0.10), rgba(0,0,0,0.10)),
            url('data:image/jpeg;base64,{DOOR_IMAGE_B64}');
          background-size: 100% 100%, 200% 100%;
          background-position: center, right center;
          border-left: 3px solid #8a6f43;
          box-shadow: -8px 0 18px rgba(0,0,0,0.35);
          animation: open-right 14s ease-in-out 1s forwards;">
      </div>


      <!-- 문구: 나타났다가 하늘로 날아가며 작아짐 -->
      <div style="
          position:absolute; left:0; right:0; bottom:22px; text-align:center;
          color:#3a2e1a; font-size:20px; font-weight:700; text-shadow: 0 1px 4px rgba(255,255,255,0.6);
          opacity:0; animation: text-life 9s ease-in 11s forwards;">
        🐾 우리 아이를 보러 갑니다 🐾
      </div>
    </div>
    <style>
      @keyframes open-left {{
        0%   {{ transform: translateX(0); }}
        100% {{ transform: translateX(-100%); }}
      }}
      @keyframes open-right {{
        0%   {{ transform: translateX(0); }}
        100% {{ transform: translateX(100%); }}
      }}
      @keyframes glow-in {{
        0%   {{ opacity: 0; }}
        55%  {{ opacity: 0; }}
        100% {{ opacity: 1; }}
      }}
      @keyframes text-life {{
        0%   {{ opacity: 0; transform: translateY(10px) scale(1); }}
        15%  {{ opacity: 1; transform: translateY(0) scale(1); }}
        55%  {{ opacity: 1; transform: translateY(0) scale(1); }}
        100% {{ opacity: 0; transform: translateY(-130px) scale(0.4); }}
      }}
      @keyframes twinkle {{
        0%, 100% {{ opacity: .3; }}
        50%      {{ opacity: 1; }}
      }}
      @keyframes big-twinkle {{
        0%, 100% {{ opacity: .5; transform: scale(1); }}
        50%      {{ opacity: 1; transform: scale(1.3); }}
      }}
      @keyframes overlay-fade-out {{
        0%   {{ opacity: 1; }}
        100% {{ opacity: 0; }}
      }}
    </style>
    <script>
      (function() {{
        var audioEl = document.getElementById('introAudio');
        if (!audioEl) return;
        setTimeout(function() {{
          var vol = 1.0;
          var fadeStep = setInterval(function() {{
            vol -= 0.06;
            if (vol <= 0) {{
              vol = 0;
              audioEl.volume = vol;
              clearInterval(fadeStep);
            }} else {{
              audioEl.volume = vol;
            }}
          }}, 100);
        }}, 18000);
      }})();
    </script>
    """
    placeholder = st.empty()
    with placeholder:
        st.components.v1.html(html, height=360)
    time.sleep(20)
    placeholder.empty()


def check_password() -> bool:
    """세션 상태에 인증 여부를 저장하는 간단한 비밀번호 게이트."""
    if st.session_state.get("authed", False):
        return True

    st.title("🐾 꼬리별")
    pw = st.text_input("비밀번호를 입력하세요", type="password", key="pw_input")
    if st.button("입장"):
        correct = st.secrets.get("APP_PASSWORD", None)
        if correct is None:
            st.error("APP_PASSWORD가 secrets에 설정되어 있지 않아요.")
        elif pw == correct:
            show_entrance_animation()
            st.session_state["authed"] = True
            st.session_state["just_entered"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸어요.")
    return False


def main():
    if not check_password():
        return

    if st.session_state.pop("just_entered", False):
        st.markdown(
            """
            <style>
            div[data-testid="stAppViewContainer"] {
                animation: page-fade-in 0.9s ease-out;
            }
            @keyframes page-fade-in {
                0%   { opacity: 0; }
                100% { opacity: 1; }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

    with st.sidebar:
        if st.button("로그아웃"):
            st.session_state["authed"] = False
            st.rerun()

    st.title("🐾 꼬리별")

    try:
        pets = load_pets()
    except Exception as e:
        st.error("GitHub 저장소 연결에 실패했어요. secrets 설정을 확인해 주세요.")
        st.exception(e)
        return

    def pet_tab_label(p):
        prefix = "·⋆✦★" if p.get("death_date", "").strip() else "🐾"
        return f"{prefix} {p['name']}"

    options = ["__home__"] + [p["id"] for p in pets] + ["__add__"]
    label_map = {"__home__": "🏠 홈", "__add__": "➕ 추가"}
    label_map.update({p["id"]: pet_tab_label(p) for p in pets})

    choice = st.selectbox(
        "이동", options, format_func=lambda k: label_map[k], label_visibility="collapsed"
    )

    if pets:
        with st.expander("🔀 탭 순서 바꾸기"):
            for i, p in enumerate(pets):
                rc1, rc2, rc3 = st.columns([5, 1, 1])
                with rc1:
                    st.write(pet_tab_label(p))
                with rc2:
                    if st.button("⬆️", key=f"up_{p['id']}", disabled=(i == 0)):
                        pets[i - 1], pets[i] = pets[i], pets[i - 1]
                        save_pets(pets)
                        st.rerun()
                with rc3:
                    if st.button("⬇️", key=f"down_{p['id']}", disabled=(i == len(pets) - 1)):
                        pets[i + 1], pets[i] = pets[i], pets[i + 1]
                        save_pets(pets)
                        st.rerun()

    st.divider()

    if choice == "__home__":
        render_home(pets)
    elif choice == "__add__":
        render_add_tab(pets)
    else:
        pet = next(p for p in pets if p["id"] == choice)
        render_pet_tab(pet, pets)


if __name__ == "__main__":
    main()
