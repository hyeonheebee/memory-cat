# 메모리 뚱냥이 🐱 (Memory Tubby Cat)

바탕화면에 둥둥 떠 있는 고양이가 **하드 용량(디스크)** 이 찰수록 **애기냥 → 돼지냥**으로 빵빵해집니다.
[RunCat](https://github.com/Kyome22/RunCat_for_macOS)의 "디스크 용량" 버전 같은 느낌이에요. macOS · Windows 둘 다 지원.

> A cute desktop pet that gets chubbier as your disk fills up. The fatter the cat, the fuller your drive. Works on macOS & Windows.

- 디스크가 찰수록 고양이가 통통해지고 살짝 튐 (램 사용량도 함께 표시)
- 드래그로 이동 / 우클릭으로 상세·테마·크기 변경
- **테마 4종** 기본 제공 + **이미지만 있으면 나만의 테마 추가**
- 설정은 자동 저장, 로그인 시 자동 실행

## 테마

| 테마 | 설명 |
|---|---|
| 귀여운 | 3D 토이 느낌 (뚱뚱할수록 눈 게슴츠레) |
| 단순한 | 심플 일러스트 뚱냥 |
| 광기 | 큰 반짝이 눈 치비냥 |
| 경각심 | 하찮은 멍냥 |

---

## 설치 — macOS

```bash
git clone https://github.com/hyeonheebee/memory-cat.git
cd memory-cat
./install_mac.command        # 더블클릭해도 됩니다
```

`python3`(3.9+)만 있으면 가상환경 만들고 의존성 설치 후 자동 실행까지 됩니다.
제거는 `./uninstall_mac.command`.

## 설치 — Windows

`windows/` 폴더의 `README.txt`를 보세요. 요약:

```bat
pip install pyside6 psutil
pythonw windows\windows_cat.pyw
```

파이썬 없이 쓰고 싶으면 `windows\build_exe.bat`로 `.exe`를 만들 수 있어요.

---

## 나만의 테마 만들기 🎨

**가로로 N단계(마름 → 뚱뚱) 늘어선 고양이 이미지 한 장**만 있으면 됩니다.
(ChatGPT 등으로 "같은 고양이가 6단계로 점점 통통해지는, 흰 배경, 한 줄" 이미지를 뽑으면 좋아요.)

```bash
# (가상환경 기준) 이미지 변환 도구 의존성
./.venv/bin/python -m pip install -r requirements-dev.txt

# 이미지 -> 테마 (흰 배경 자동 제거 + 정렬 + 단계화)
./.venv/bin/python import_theme.py 내고양이.png 내테마이름
```

앱을 다시 실행하면 우클릭 **테마** 메뉴에 `내테마이름`이 자동으로 생깁니다.
(테마는 `frames/<이름>/` 폴더를 자동 인식해요.)

코드로 그리는 테마는 `python generate_frames.py`로 다시 뽑을 수 있습니다.

---

## 구조

```
desktop_cat.py      macOS 앱 (PyObjC)
windows/            Windows 앱 (PySide6)
metrics.py          디스크/메모리 측정 (공통)
generate_frames.py  코드 테마 프레임 생성
import_theme.py     이미지 -> 테마 변환
frames/<theme>/     테마별 프레임 PNG
```

## 만든이 / License

심현희 ([@hyeonheebee](https://github.com/hyeonheebee)) + Claude 🐾 · [MIT](LICENSE)
