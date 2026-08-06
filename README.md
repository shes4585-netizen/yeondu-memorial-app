# 🐾 우리 아이들 (반려동물 추억 앱)

Streamlit + GitHub 저장소로 동작하는 사진/댓글 기록 앱입니다.
사진, 댓글, 프로필 정보가 전부 여러분의 GitHub 저장소 `data/` 폴더에
커밋되어 영구 저장되므로, Streamlit Cloud가 재시작돼도 데이터가 사라지지 않습니다.

## 1. 데이터를 저장할 GitHub 저장소 준비
1. github.com에서 새 저장소를 하나 만듭니다. (Private 추천, 예: `pet-memorial-data`)
   - 이 앱 코드를 올릴 저장소와 같아도 되고, 데이터 전용으로 따로 만들어도 됩니다.
2. GitHub → Settings → Developer settings → Personal access tokens →
   **Fine-grained token** 생성
   - Repository access: 위에서 만든 저장소만 선택
   - Permissions: `Contents` = Read and write
3. 발급된 토큰을 복사해둡니다. (한 번만 보여줍니다)

## 2. 로컬에서 테스트
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml 안의 GITHUB_TOKEN, GITHUB_REPO 값을 채워넣기
streamlit run app.py
```

## 3. Streamlit Community Cloud 배포 (무료, 모바일 브라우저로 접속 가능)
1. 이 앱 코드(app.py, github_storage.py, backup_utils.py, requirements.txt)를
   GitHub 저장소에 올립니다. (`.streamlit/secrets.toml`은 절대 올리지 마세요 — 토큰 노출됨)
2. https://share.streamlit.io 접속 → New app → 방금 올린 저장소 선택
3. 앱 설정의 **Secrets** 탭에 `secrets.toml.example` 내용을 값 채워서 붙여넣기
4. 배포하면 나오는 URL을 모바일 브라우저 즐겨찾기/홈 화면에 추가하면
   앱처럼 사용할 수 있습니다.

## 기능
- 탭별 반려동물 등록/수정/삭제 (앱 안에서 동적으로 추가 가능)
- 사진 업로드 + 사진마다 댓글
- 생년월일/사망년월일/좋아했던 음식/특징 기록
- 첫 번째 "홈" 탭에서 전체 최신 사진/댓글 모아보기
- 반려동물별 백업: zip 최대 압축 + 지정 용량 초과 시 자동 분할
  (다운로드한 파일 안의 merge.py 실행하면 원본 zip으로 복원)

## 폴더 구조 (GitHub 저장소 안)
```
data/
  pets.json                 # 전체 반려동물 목록/프로필
  {pet_id}/
    gallery.json            # 사진 목록 + 댓글
    photos/
      xxxx_사진.jpg
```
