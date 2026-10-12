import io
import time
import uuid
import datetime as dt

import streamlit as st
from PIL import Image, ImageOps

import github_storage as gh
from intro_audio import INTRO_AUDIO_B64
from sky_image import SKY_IMAGE_B64
from sfx_audio import SFX_AUDIO_B64
from backup_utils import build_pet_zip, make_downloadable_backup

st.set_page_config(page_title="꼬리별", page_icon="🐾", layout="centered")

PETS_PATH = "data/pets.json"
MAX_DIMENSION = 1600  # 긴 변 기준 최대 픽셀 (모바일 화면에 충분한 크기)
JPEG_QUALITY = 85
MAX_RAW_BYTES = 10 * 1024 * 1024  # GIF/MP4 업로드 상한 10MB (원본 그대로 저장)
RAW_EXTS = ("gif", "mp4")


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


def fetch_media(pet_id, filename):
    """사진/영상 파일을 (bytes, sha)로 가져온다. 큰 파일(gif/mp4)은 세션에 기억해 재다운로드를 줄인다."""
    path = f"data/{pet_id}/photos/{filename}"
    cache = st.session_state.setdefault("_media_cache", {})
    if path in cache:
        return cache[path]
    got = gh.get_file(path)
    if got and filename.lower().endswith(RAW_EXTS):
        cache[path] = got
    return got


def show_media(filename, data):
    if filename.lower().endswith(".mp4"):
        st.video(data)
    else:
        st.image(data, use_container_width=True)


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
        got = fetch_media(e["pet_id"], e["filename"])
        cols = st.columns([1, 2])
        with cols[0]:
            if got:
                show_media(e["filename"], got[0])
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

    st.markdown("#### 📸 사진/영상 올리기")
    uploaded = st.file_uploader("사진·GIF·MP4 선택 (GIF/MP4는 10MB까지)",
                                type=["jpg", "jpeg", "png", "webp", "gif", "mp4"], key=f"upl_{pet_id}")
    if uploaded is not None:
        raw_ext = uploaded.name.lower().rsplit(".", 1)[-1]
        is_raw = raw_ext in RAW_EXTS
        too_big = is_raw and uploaded.size > MAX_RAW_BYTES
        if too_big:
            st.error(f"{raw_ext.upper()}는 10MB까지 올릴 수 있어요. (현재 {uploaded.size / 1024 / 1024:.1f}MB)")
        if st.button("업로드", key=f"upl_btn_{pet_id}", disabled=too_big):
            if is_raw:
                resized_bytes, ext = uploaded.getvalue(), raw_ext  # 움직임/영상 유지를 위해 변환하지 않음
            else:
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
        got = fetch_media(pet_id, item["filename"])
        if got:
            show_media(item["filename"], got[0])
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
                st.session_state.get("_media_cache", {}).pop(f"data/{pet_id}/photos/{item['filename']}", None)
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
                got = fetch_media(pet_id, item["filename"])
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

    # 반짝임 추가: 잔별 + 십자 반짝이(스파클)
    import random
    rnd = random.Random(7)
    for _ in range(36):
        left, top = rnd.uniform(2, 98), rnd.uniform(3, 52)
        size = rnd.choice([1.5, 2, 2.5, 3])
        dur, delay = rnd.uniform(1.6, 3.6), rnd.uniform(0, 4)
        stars += (
            f'<div style="position:absolute; left:{left:.1f}%; top:{top:.1f}%; '
            f'width:{size}px; height:{size}px; background:#fff; border-radius:50%; '
            f'box-shadow:0 0 5px 1px rgba(200,225,255,0.9); '
            f'opacity:.2; animation: twinkle {dur:.1f}s ease-in-out {delay:.1f}s infinite;"></div>'
        )
    for _ in range(12):
        left, top = rnd.uniform(5, 95), rnd.uniform(5, 50)
        size = rnd.choice([16, 20, 26, 32])
        dur, delay = rnd.uniform(2.4, 4.2), rnd.uniform(0, 5)
        stars += (
            f'<div class="spk" style="left:{left:.1f}%; top:{top:.1f}%; '
            f'width:{size}px; height:{size}px; animation-duration:{dur:.1f}s; animation-delay:{delay:.1f}s;"></div>'
        )

    html = f"""
    <audio id="introAudio" autoplay>
      <source src="data:audio/mp4;base64,{INTRO_AUDIO_B64}" type="audio/mp4">
    </audio>
    <audio id="sfxAudio" autoplay>
      <source src="data:audio/mp4;base64,{SFX_AUDIO_B64}" type="audio/mp4">
    </audio>
    <div id="room">
      <!-- 실내 안테나 (토끼 귀) -->
      <div id="ant-base"></div>
      <div class="rod" id="rod-l"><i></i></div>
      <div class="rod" id="rod-r"><i></i></div>

      <!-- 자바라 TV 본체 -->
      <div id="cabinet">
        <div id="screen">
          <div id="sky-bg"></div>
          {stars}
          <div id="glow"></div>
          <div id="crt"></div>
          <div id="msg">🐾 우리 아이를 보러 갑니다 🐾</div>
        </div>
        <div id="side">
          <div class="plate">꼬리별</div>
          <div class="knob"></div>
          <div class="knob"></div>
          <div class="grille"></div>
        </div>
        <div id="shutter">
          <div id="door-left"><b class="handle" style="right:5px"></b></div>
          <div id="door-right"><b class="handle" style="left:5px"></b></div>
        </div>
        <div id="power">
          <span class="plabel">POWER</span>
          <div id="led"></div>
          <div id="sw"><div id="lever"></div></div>
        </div>
      </div>
      <div class="leg" id="leg-l"></div>
      <div class="leg" id="leg-r"></div>
      <div id="floor"></div>
    </div>
    <style>
      #sky-bg {{ background-image: url('data:image/jpeg;base64,{SKY_IMAGE_B64}'); background-size: cover; background-position: center; }}
      body {{ margin:0; }}
      #room {{
        position:relative; width:100%; height:340px; overflow:hidden; border-radius:12px;
        background: radial-gradient(ellipse at 50% 40%, #3a2a1c 0%, #20160e 70%, #120c07 100%);
        animation: overlay-fade-out 2s ease-in 18s forwards;
      }}
      #cabinet {{
        position:absolute; left:50%; top:58px; transform:translateX(-50%);
        width:90%; max-width:470px; height:244px; box-sizing:border-box;
        display:flex; gap:8px; padding:12px 12px 32px; border-radius:10px;
        border:3px solid #3d2410;
        background:
          repeating-linear-gradient(92deg, rgba(0,0,0,0) 0 7px, rgba(0,0,0,.07) 7px 8px, rgba(255,255,255,.03) 8px 12px),
          linear-gradient(180deg, #9a6532 0%, #7a4c22 55%, #6a401c 100%);
        box-shadow: 0 10px 22px rgba(0,0,0,.55), inset 0 2px 3px rgba(255,220,160,.35);
        z-index:2;
      }}
      #screen {{
        position:relative; flex:1; overflow:hidden; border-radius:26px / 22px;
        border:6px solid #17100a; background:#06122a;
        box-shadow: inset 0 0 22px rgba(0,0,0,.9), 0 0 0 2px #5a3a1a;
      }}
      #sky-bg {{ position:absolute; inset:0; background-image: url('data:image/jpeg;base64,{SKY_IMAGE_B64}'); background-size: cover; background-position: center; }}
      #glow {{
        position:absolute; left:50%; top:50%; width:200px; height:200px; transform:translate(-50%,-50%);
        border-radius:50%; opacity:0; animation: glow-in 20s ease-in forwards;
        background: radial-gradient(circle, rgba(255,244,214,.45) 0%, rgba(255,244,214,.15) 45%, rgba(255,244,214,0) 75%);
      }}
      #crt {{
        position:absolute; inset:0; pointer-events:none;
        background:
          repeating-linear-gradient(0deg, rgba(0,0,0,.06) 0 1px, rgba(0,0,0,0) 1px 3px),
          radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(0,0,0,.55) 100%);
      }}
      #door-left, #door-right {{
        position:absolute; top:0; width:50%; height:100%; will-change:transform;
        background:
          repeating-linear-gradient(90deg, #c08a4c 0, #d3a266 5px, #9a6630 9px, #6b4220 12px, #8a5a2b 14px, #b98448 18px);
        box-shadow: inset 0 0 14px rgba(0,0,0,.45);
      }}
      #door-left  {{ left:0;  transform-origin:left center;  border-right:2px solid #4a2c12; animation: open-left 14s ease-in-out 2.4s forwards; }}
      #door-right {{ right:0; transform-origin:right center; border-left:2px solid #4a2c12;  animation: open-right 14s ease-in-out 2.4s forwards; }}
      .handle {{ position:absolute; top:50%; width:7px; height:28px; margin-top:-14px; border-radius:4px;
        background: linear-gradient(90deg,#f3dc9a,#b08a32); box-shadow:0 1px 3px rgba(0,0,0,.6); }}
      #msg {{
        position:absolute; left:0; right:0; bottom:16px; text-align:center; padding:0 6px;
        color:#fff8e6; font-size:15px; font-weight:700; text-shadow:0 1px 6px rgba(0,0,0,.9);
        opacity:0; animation: text-life 9s ease-in 11s forwards;
      }}
      #side {{
        flex:0 0 58px; border-radius:8px; padding:8px 0; box-sizing:border-box;
        display:flex; flex-direction:column; align-items:center; gap:10px;
        background: linear-gradient(180deg,#5a3719,#46280f); box-shadow: inset 0 0 8px rgba(0,0,0,.6);
      }}
      .plate {{ font-size:9px; font-weight:700; color:#3a2a08; padding:2px 5px; border-radius:2px;
        background:linear-gradient(180deg,#f0d98e,#b8913a); }}
      .knob {{ width:30px; height:30px; border-radius:50%; position:relative;
        background: radial-gradient(circle at 35% 30%, #f6ead0, #b9a47a 60%, #6e5c3a);
        box-shadow: 0 2px 4px rgba(0,0,0,.7); }}
      .knob::after {{ content:""; position:absolute; left:50%; top:3px; width:2px; height:9px; margin-left:-1px; background:#3a2a10; transform-origin:1px 12px; transform:rotate(35deg); }}
      .grille {{ flex:1; width:36px; border-radius:4px;
        background: repeating-linear-gradient(0deg,#1a0f06 0 2px,#5a3a1a 2px 5px); box-shadow: inset 0 0 4px #000; }}
      .leg {{ position:absolute; top:298px; width:15px; height:40px; z-index:1;
        background: linear-gradient(90deg,#7a4c22,#5a3517); border-radius:2px 2px 5px 5px; }}
      #leg-l {{ left:calc(50% - min(45%,235px) + 14px); transform:rotate(7deg); }}
      #leg-r {{ left:calc(50% + min(45%,235px) - 29px); transform:rotate(-7deg); }}
      #floor {{ position:absolute; left:10%; right:10%; bottom:2px; height:12px; border-radius:50%;
        background: radial-gradient(ellipse, rgba(0,0,0,.55), rgba(0,0,0,0) 70%); }}
      #ant-base {{ position:absolute; left:50%; top:50px; width:44px; height:12px; margin-left:-22px; z-index:3;
        border-radius:22px 22px 4px 4px; background:linear-gradient(180deg,#2c2c2c,#101010); box-shadow:0 2px 3px rgba(0,0,0,.6); }}
      .rod {{ position:absolute; left:50%; top:52px; width:3px; height:58px; margin-left:-1px; z-index:2;
        background:linear-gradient(90deg,#e6e6e6,#8c8c8c); transform-origin:50% 100%; margin-top:-48px; border-radius:2px; }}
      .rod i {{ position:absolute; top:-5px; left:-3px; width:9px; height:9px; border-radius:50%;
        background:radial-gradient(circle at 35% 30%,#fff,#9a9a9a); }}
      #rod-l {{ transform:rotate(-30deg); }}
      #rod-r {{ transform:rotate(30deg); }}
      #shutter {{ position:absolute; left:12px; right:12px; top:12px; bottom:32px; z-index:5; border-radius:8px; overflow:hidden; pointer-events:none; }}
      #power {{ position:absolute; right:16px; bottom:7px; height:18px; display:flex; align-items:center; gap:7px; z-index:6; }}
      .plabel {{ font-size:8px; font-weight:700; letter-spacing:1px; color:#e8cf94; text-shadow:0 1px 1px #2a1606; }}
      #led {{ position:relative; width:9px; height:9px; border-radius:50%; background:radial-gradient(circle at 35% 30%,#5a1a14,#2a0806);
        box-shadow: 0 0 0 2px #3a2410, inset 0 1px 2px rgba(0,0,0,.7); animation: led-pulse 2.4s ease-in-out 1.8s infinite; }}
      #led::before {{ content:""; position:absolute; inset:0; border-radius:50%; opacity:0;
        background:radial-gradient(circle at 35% 30%,#ffb0a0,#ff2a1a 55%,#c00);
        box-shadow: 0 0 6px 2px rgba(255,40,20,.9), 0 0 14px 5px rgba(255,40,20,.45);
        animation: led-on .3s ease-out 1.5s forwards; }}
      #sw {{ position:relative; width:30px; height:16px; border-radius:8px; background:#1d1208; box-shadow: inset 0 1px 3px #000, 0 0 0 2px #3a2410;
        animation: sw-bg .2s linear 1.1s forwards; }}
      #lever {{ position:absolute; left:2px; top:2px; width:12px; height:12px; border-radius:50%;
        background: radial-gradient(circle at 35% 30%,#f6ead0,#a8956a); box-shadow:0 1px 2px rgba(0,0,0,.8);
        animation: sw-on .25s ease-out 1.1s forwards; }}
      @keyframes sw-on {{ 0% {{ transform:translateX(0) scale(1); }} 40% {{ transform:translateX(5px) scale(.88); }} 100% {{ transform:translateX(14px) scale(1); }} }}
      @keyframes sw-bg {{ to {{ background:#3b1d12; }} }}
      @keyframes led-on {{ 0% {{ opacity:0; }} 35% {{ opacity:1; }} 55% {{ opacity:.55; }} 100% {{ opacity:1; }} }}
      @keyframes led-pulse {{ 0%,100% {{ filter:brightness(1); }} 50% {{ filter:brightness(1.35); }} }}
      @keyframes open-left {{
        0%   {{ transform: scaleX(1); }}
        100% {{ transform: scaleX(0.07); }}
      }}
      @keyframes open-right {{
        0%   {{ transform: scaleX(1); }}
        100% {{ transform: scaleX(0.07); }}
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
        100% {{ opacity: 0; transform: translateY(-110px) scale(0.4); }}
      }}
      .spk {{
        position:absolute; opacity:0; transform:translate(-50%,-50%) scale(.3);
        background:
          radial-gradient(circle, #fff 0 10%, rgba(255,255,255,0) 45%),
          linear-gradient(90deg, rgba(255,255,255,0) 0%, #fff 50%, rgba(255,255,255,0) 100%) center/100% 2px no-repeat,
          linear-gradient(0deg, rgba(255,255,255,0) 0%, #fff 50%, rgba(255,255,255,0) 100%) center/2px 100% no-repeat;
        filter: drop-shadow(0 0 4px rgba(190,220,255,0.95));
        animation: spk-pulse 3s ease-in-out infinite;
      }}
      @keyframes spk-pulse {{
        0%, 100% {{ opacity:0; transform:translate(-50%,-50%) scale(.3) rotate(0deg); }}
        50%      {{ opacity:1; transform:translate(-50%,-50%) scale(1.15) rotate(45deg); }}
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
        var sfx = document.getElementById('sfxAudio');
        if (sfx) {{ try {{ var pr = sfx.play(); if (pr && pr.catch) pr.catch(function(){{}}); }} catch (e) {{}} }}
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
