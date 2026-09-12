# 윈도우판 진단 + 커스텀 펫 테마 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 윈도우판 뚱냥이에 "🐾 뭘 먹은 거야?" 진단(설명만, 정리 없음)과 반려동물 사진으로 테마 만들기를 넣는다.

**Architecture:** 맥·윈도우가 **같은 엔진을 공유**한다. `brain.py`(진단)와 `vision_theme.py`·`import_theme.py`(테마 생성)는 이미 플랫폼 의존이 거의 없다. 막고 있는 건 두 가지뿐이다 — `apppaths.py` 가 맥 경로로 박혀 있고, `brain.diagnose()` 가 맥 전용 정리 후보를 **무조건** 수집한다. 이 둘을 열고, 윈도우 쪽에는 Qt UI만 새로 붙인다.

**Tech Stack:** Python 3.12 / PySide6 (윈도우 UI) / openai · pydantic · python-dotenv (진단) / Pillow · numpy (테마) / PyInstaller `--onefile`

**Spec:** 이 문서에 인라인. 아래 "결정된 것" 이 스펙이다.

---

## 결정된 것 (스펙)

| 항목 | 결정 |
|---|---|
| 윈도우 진단 | **설명만.** 왜 느린지 말해준다 |
| 윈도우 정리(파일 삭제) | **넣지 않는다.** 대신 결과창에 경고 문구 |
| 경고 문구 | "삭제는 되돌릴 수 없습니다. 직접 확인하고 지워 주세요." 취지 |
| 윈도우 커스텀 테마 | **넣는다** |
| AI 기능 | **선택 사항.** `OPENAI_API_KEY` 없으면 지금과 동일하게 동작 |
| 맥 | **건드리지 않는다.** 정리 기능도 그대로 |
| 실기 검증 | 회사 윈도우 PC + 친구 PC 로 확인 가능 |

## Global Constraints

- **공용 문구는 두 언어 모두 넣는다.** `i18n.py` 의 `ko` 와 `en` 양쪽. v0.3.0 에서 맥만 고쳐 윈도우 정보창이 통째로 비어 나간 사고가 있었다. `tr()` 은 키가 없으면 KeyError 를 내고, `windows_cat.refresh()` 가 예외를 삼켜서 **앱은 멀쩡히 도는데 창만 빈다.**
- **`windows/build_exe.bat` 의 `--hidden-import` 를 빠뜨리면 exe 가 켜지자마자 조용히 죽는다** (`--noconsole`). 루트 모듈을 새로 쓰면 반드시 추가하고 `WindowsBuildScriptTests` 도 같이 고친다.
- **맥에서 돌릴 수 있는 테스트만 쓴다.** 맥 개발 환경에는 PySide6 가 없다. Qt 를 import 하는 코드는 테스트하지 않는다 — 그래서 **순수 로직을 Qt 밖으로 뺀다**(Task 5·6).
- **요구사항 상·하한을 모두 건다.** `windows/requirements.txt` 는 ASCII 만. 한국어 주석을 넣으면 한국어 윈도우(cp949)에서 `UnicodeDecodeError` 로 설치가 깨진다.
- **파일을 지우는 코드는 이 계획에 없다.** `safe_trash`, `collect_cleanup_candidates`, 허용 목록은 윈도우에서 **호출되지 않아야** 한다. 테스트로 못 박는다.
- 버전·릴리스는 이 계획 범위 밖. 머지 후 별도로 v0.4.0 을 굽는다.

---

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `apppaths.py` | 사용자 데이터 위치. **윈도우 분기 추가** | 수정 |
| `brain.py` | 진단. **정리 없이도 돌 수 있게** 문 하나 열기 | 수정 |
| `i18n.py` | 새 문구(메뉴·경고·오류) 두 언어 | 수정 |
| `windows/win_ai.py` | **신규.** Qt 없는 순수 로직 — 무엇을 보여줄지, 어디에 쓸지, 어떤 오류 문구인지 | 생성 |
| `windows/win_ai_ui.py` | **신규.** PySide6 대화상자. 얇게 유지 | 생성 |
| `windows/windows_cat.pyw` | 우클릭 메뉴에 항목 2개 추가. 나머지는 위 두 파일에 위임 | 수정 |
| `windows/requirements.txt` | openai·pydantic·python-dotenv·Pillow·numpy 추가 | 수정 |
| `windows/build_exe.bat` | `--hidden-import` 추가 | 수정 |
| `tests/test_apppaths.py` | 신규 또는 기존에 추가 | 수정 |
| `tests/test_brain.py` | 정리 없는 진단 검사 | 수정 |
| `tests/test_win_ai.py` | **신규.** `win_ai` 순수 로직 | 생성 |
| `tests/test_windows_build_script.py` | hidden-import 검사 확장 | 수정 |
| `README.md` | "네트워크 요청 없음" 문구 정정 | 수정 |

---

### Task 1: `apppaths` 에 윈도우 경로를 연다

맥 전용으로 박혀 있어서 윈도우에서 쓰면 `C:\Users\me\Library\Application Support\...` 같은 엉뚱한 폴더가 만들어진다.

**Files:**
- Modify: `apppaths.py:63-96`
- Test: `tests/test_apppaths.py`

**Interfaces:**
- Produces: `apppaths.user_data_dir() -> Path` (윈도우면 `%APPDATA%\Memory Cat`), `apppaths.log_dir() -> Path`, `apppaths.user_frames_dir()`, `apppaths.dotenv_candidates()` — 이름·시그니처 그대로, 동작만 플랫폼에 따라 갈린다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_apppaths.py
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import apppaths


class UserDataDirTests(unittest.TestCase):
    def setUp(self):
        # MEMORY_CAT_HOME 이 걸려 있으면 플랫폼 분기를 건너뛴다
        self._saved = os.environ.pop(apppaths.HOME_ENV, None)

    def tearDown(self):
        if self._saved is not None:
            os.environ[apppaths.HOME_ENV] = self._saved

    def test_windows_uses_appdata(self):
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(
                apppaths.user_data_dir(),
                Path(r"C:\Users\me\AppData\Roaming") / apppaths.APP_NAME)

    def test_windows_without_appdata_falls_back_to_home(self):
        """APPDATA 는 보통 있지만, 없다고 앱이 죽으면 안 된다."""
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPDATA", None)
            self.assertEqual(
                apppaths.user_data_dir(),
                Path.home() / "AppData" / "Roaming" / apppaths.APP_NAME)

    def test_mac_is_unchanged(self):
        with patch.object(apppaths.sys, "platform", "darwin"):
            self.assertEqual(
                apppaths.user_data_dir(),
                Path.home() / "Library" / "Application Support" / apppaths.APP_NAME)

    def test_the_override_still_wins_on_both(self):
        for platform in ("win32", "darwin"):
            with self.subTest(platform=platform), \
                 patch.object(apppaths.sys, "platform", platform), \
                 patch.dict(os.environ, {apppaths.HOME_ENV: "/tmp/cat-home"}):
                self.assertEqual(apppaths.user_data_dir(), Path("/tmp/cat-home"))

    def test_windows_log_dir_sits_under_user_data(self):
        with patch.object(apppaths.sys, "platform", "win32"), \
             patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(apppaths.log_dir(),
                             apppaths.user_data_dir() / "Logs")
```

- [ ] **Step 2: 실패하는지 확인한다**

Run: `./.venv/bin/python -m pytest tests/test_apppaths.py -v`
Expected: FAIL — `test_windows_uses_appdata` 가 `~/Library/Application Support/Memory Cat` 를 돌려준다. `apppaths` 에 `sys` import 가 없어 `AttributeError` 가 먼저 날 수도 있다.

- [ ] **Step 3: 최소 구현**

```python
# apppaths.py 상단에 sys import 추가

def user_data_dir() -> Path:
    """설정·커스텀 테마·API 키가 사는 곳. 없으면 만들지는 않는다.

    맥은 ``~/Library/Application Support/Memory Cat``,
    윈도우는 ``%APPDATA%\\Memory Cat`` 을 쓴다. 윈도우판이 exe 옆에 설정을
    두던 방식은 Program Files 처럼 쓰기 권한이 없는 곳에 깔리면 깨진다.
    """
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA")
        if roaming:
            return Path(roaming) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path.home() / "Library" / "Application Support" / APP_NAME


def log_dir() -> Path:
    if sys.platform == "win32":
        return user_data_dir() / "Logs"
    return Path.home() / "Library" / "Logs" / APP_NAME
```

`user_frames_dir()`·`config_file()`·`dotenv_candidates()` 는 `user_data_dir()` 위에 얹혀 있으므로 **고칠 필요가 없다.**

- [ ] **Step 4: 통과 확인**

Run: `./.venv/bin/python -m pytest tests/test_apppaths.py -v`
Expected: PASS (5개)

- [ ] **Step 5: 맥 회귀 확인**

Run: `./.venv/bin/python -m pytest tests -q`
Expected: 기존 215 + 신규 5 통과

- [ ] **Step 6: 커밋**

```bash
git add apppaths.py tests/test_apppaths.py
git commit -m "feat: apppaths 에 윈도우 경로를 연다"
```

---

### Task 2: 정리 없이도 진단이 돌게 한다

지금 `brain.diagnose()` 는 [brain.py:546](../../../brain.py) 에서 `collect_cleanup_candidates()` 를 **무조건** 부른다. 그 함수는 `~/Library/Caches/...`, `~/.Trash`, Xcode DerivedData 를 뒤진다. 윈도우에서 부르면 의미도 없고, 무엇보다 **파일 삭제 코드에 발을 들이게 된다.**

**Files:**
- Modify: `brain.py:525-600`
- Test: `tests/test_brain.py`

**Interfaces:**
- Produces: `brain.diagnose(..., include_cleanup: bool = True)`. `False` 면 `collect_cleanup_candidates` 를 **부르지 않고**, 결과의 `recommendations` 는 빈 리스트, `estimated_bytes` 는 0 이다. 나머지 키(`why_slow`, `one_line_advice`, `metrics`)는 그대로.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_brain.py 에 추가
class DiagnoseWithoutCleanupTests(unittest.TestCase):
    """윈도우판은 파일을 지우지 않는다. 후보를 모으지도 않아야 한다."""

    def test_it_never_touches_the_cleanup_scanner(self):
        with patch.object(brain, "collect_cleanup_candidates") as scanner, \
             patch.object(brain, "_load_api_key", return_value=None):
            result = brain.diagnose(language="ko", include_cleanup=False)
        scanner.assert_not_called()
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["estimated_bytes"], 0)

    def test_the_explanation_still_comes_back(self):
        with patch.object(brain, "_load_api_key", return_value=None):
            result = brain.diagnose(language="ko", include_cleanup=False)
        self.assertTrue(result["why_slow"], "왜 느린지 설명이 비었다")
        self.assertTrue(result["one_line_advice"])

    def test_the_default_still_collects(self):
        """맥 동작이 바뀌면 안 된다."""
        with patch.object(brain, "collect_cleanup_candidates",
                          return_value=[]) as scanner, \
             patch.object(brain, "_load_api_key", return_value=None):
            brain.diagnose(language="ko")
        scanner.assert_called_once()
```

- [ ] **Step 2: 실패하는지 확인한다**

Run: `./.venv/bin/python -m pytest tests/test_brain.py -k WithoutCleanup -v`
Expected: FAIL — `diagnose() got an unexpected keyword argument 'include_cleanup'`

- [ ] **Step 3: 최소 구현**

```python
def diagnose(
    metrics_snapshot: Optional[Mapping[str, Any]] = None,
    personality: Optional[str] = None,
    custom_personality: Optional[str] = None,
    language: str = LANGUAGE_KO,
    include_cleanup: bool = True,
) -> Dict[str, Any]:
    """...

    ``include_cleanup=False`` 면 정리 후보를 **수집조차 하지 않는다.**
    윈도우판이 쓰는 길이다 — 거기엔 지울 수 있는 안전한 목록도, 되돌릴 수
    있는 휴지통 API 도 없다. 설명만 한다.
    """
    ...
    candidates = collect_cleanup_candidates(language=lang) if include_cleanup else []
```

나머지는 그대로 둔다. `_assemble_result` 는 빈 리스트를 받으면 추천을 만들지 않는다(`by_category` 가 비므로).

- [ ] **Step 4: 통과 확인**

Run: `./.venv/bin/python -m pytest tests/test_brain.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add brain.py tests/test_brain.py
git commit -m "feat: 정리 없이 설명만 하는 진단 경로를 연다"
```

---

### Task 3: 새 문구를 두 언어에 넣는다

**Files:**
- Modify: `i18n.py` (`_STRINGS["ko"]`, `_STRINGS["en"]` 양쪽)
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: 새 키 — `menu_diagnose`, `menu_make_theme`, `diagnosis_title`, `windows_delete_warning`, `theme_consent_title`, `theme_consent_body`, `theme_working`, `theme_done`, `theme_error_format`, `no_api_key_title`, `no_api_key_body`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_i18n.py 에 추가
NEW_KEYS = (
    "menu_diagnose", "menu_make_theme", "diagnosis_title",
    "windows_delete_warning", "theme_consent_title", "theme_consent_body",
    "theme_working", "theme_done", "theme_error_format",
    "no_api_key_title", "no_api_key_body",
)


class WindowsFeatureStringsTests(unittest.TestCase):
    def test_every_new_key_exists_in_both_languages(self):
        """한쪽만 넣으면 그 언어에서 창이 통째로 빈다. v0.3.0 의 사고다."""
        for key in NEW_KEYS:
            for language in ("ko", "en"):
                with self.subTest(key=key, language=language):
                    self.assertIn(key, i18n._STRINGS[language])
                    self.assertTrue(i18n._STRINGS[language][key].strip())

    def test_the_delete_warning_says_it_cannot_be_undone(self):
        ko = i18n.tr("ko", "windows_delete_warning")
        en = i18n.tr("en", "windows_delete_warning")
        self.assertIn("되돌릴 수 없", ko)
        self.assertIn("cannot be undone", en.lower())
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -k WindowsFeature -v`
Expected: FAIL — 키 없음

- [ ] **Step 3: 구현**

```python
# i18n.py — _STRINGS["ko"] 에
        "menu_diagnose": "🐾 뭘 먹은 거야?",
        "menu_make_theme": "내 반려동물로 테마 만들기…",
        "diagnosis_title": "🐾 뭘 먹었냐면",
        "windows_delete_warning": (
            "윈도우판은 파일을 지우지 않습니다. 지운 파일은 되돌릴 수 없으니 "
            "위 항목은 직접 확인하고 지워 주세요."
        ),
        "theme_consent_title": "사진을 OpenAI 로 보냅니다",
        "theme_consent_body": (
            "고른 사진 한 장이 OpenAI 로 올라갑니다. 파일 이름과 경로는 "
            "보내지 않습니다. 계속할까요?"
        ),
        "theme_working": "테마를 만드는 중이에요… 1~2분 걸립니다.",
        "theme_done": "'{name}' 테마를 만들었어요. 지금 적용합니다.",
        "theme_error_format": "PNG, JPEG, WebP 파일만 됩니다.",
        "no_api_key_title": "OpenAI 키가 필요해요",
        "no_api_key_body": (
            "이 기능은 선택 사항입니다. {path} 에 OPENAI_API_KEY 를 넣으면 "
            "쓸 수 있어요. 키가 없어도 뚱냥이는 그대로 동작합니다."
        ),
```

```python
# i18n.py — _STRINGS["en"] 에
        "menu_diagnose": "🐾 What did you eat?",
        "menu_make_theme": "Make a theme from my pet…",
        "diagnosis_title": "🐾 Here's what he ate",
        "windows_delete_warning": (
            "The Windows build does not delete anything. Deleting a file "
            "cannot be undone, so please check and remove these yourself."
        ),
        "theme_consent_title": "This sends your photo to OpenAI",
        "theme_consent_body": (
            "The one photo you pick is uploaded to OpenAI. File names and "
            "paths are never sent. Continue?"
        ),
        "theme_working": "Building your theme… this takes a minute or two.",
        "theme_done": "Built the '{name}' theme. Applying it now.",
        "theme_error_format": "Only PNG, JPEG, and WebP files work.",
        "no_api_key_title": "An OpenAI key is needed",
        "no_api_key_body": (
            "This feature is optional. Put OPENAI_API_KEY in {path} to use "
            "it. Memory Cat works fine without a key."
        ),
```

- [ ] **Step 4: 통과 확인**

Run: `./.venv/bin/python -m pytest tests/test_i18n.py -v`

- [ ] **Step 5: 커밋**

```bash
git add i18n.py tests/test_i18n.py
git commit -m "feat: 윈도우 진단·테마 문구를 두 언어에 넣는다"
```

---

### Task 4: 윈도우 의존성과 빌드 스크립트를 연다

`--hidden-import` 를 빠뜨리면 **빌드는 되고 exe 가 켜자마자 조용히 죽는다.**

**Files:**
- Modify: `windows/requirements.txt`, `windows/build_exe.bat`
- Test: `tests/test_windows_build_script.py`

**Interfaces:**
- Produces: exe 안에 `brain`, `personality`, `vision_theme`, `import_theme`, `apppaths` 가 들어간다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_windows_build_script.py 에 추가
ROOT_MODULES_THE_WINDOWS_APP_IMPORTS = (
    "i18n", "metrics", "apppaths", "brain", "personality",
    "vision_theme", "import_theme",
)


class HiddenImportTests(unittest.TestCase):
    def test_every_root_module_is_hidden_imported(self):
        """PyInstaller 는 --paths 만으로는 루트 모듈을 안 끌고 간다.
        빠뜨리면 --noconsole 이라 오류 한 줄 없이 죽는다."""
        script = (REPO / "windows" / "build_exe.bat").read_text(encoding="utf-8")
        for module in ROOT_MODULES_THE_WINDOWS_APP_IMPORTS:
            with self.subTest(module=module):
                self.assertIn(f"--hidden-import {module}", script)

    def test_requirements_stay_ascii(self):
        """한국어 윈도우(cp949)에서 pip 가 UnicodeDecodeError 로 죽는다."""
        raw = (REPO / "windows" / "requirements.txt").read_bytes()
        raw.decode("ascii")

    def test_the_ai_packages_are_listed(self):
        text = (REPO / "windows" / "requirements.txt").read_text(encoding="ascii")
        for package in ("openai", "pydantic", "python-dotenv", "Pillow", "numpy"):
            with self.subTest(package=package):
                self.assertIn(package, text)
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/bin/python -m pytest tests/test_windows_build_script.py -v`
Expected: FAIL — `--hidden-import brain` 없음

- [ ] **Step 3: 구현**

`windows/requirements.txt` 에 추가 (ASCII 주석만):

```
# Optional AI features: diagnosis (brain.py) and custom pet themes
# (vision_theme.py). The app still runs without an OPENAI_API_KEY.
openai>=2.46,<3
pydantic>=2.9,<3
python-dotenv>=1.2,<2
Pillow>=10,<13
numpy>=1.24,<3
```

`windows/build_exe.bat` 의 PyInstaller 줄에 추가:

```
--hidden-import apppaths --hidden-import brain --hidden-import personality ^
--hidden-import vision_theme --hidden-import import_theme ^
```

- [ ] **Step 4: 통과 확인**

Run: `./.venv/bin/python -m pytest tests/test_windows_build_script.py -v`

- [ ] **Step 5: 커밋**

```bash
git add windows/requirements.txt windows/build_exe.bat tests/test_windows_build_script.py
git commit -m "build: 윈도우 exe 에 AI 모듈을 넣는다"
```

---

### Task 5: 윈도우 진단 — 순수 로직 먼저

Qt 를 import 하는 코드는 맥에서 테스트할 수 없다. **무엇을 보여줄지 정하는 부분을 Qt 밖으로 뺀다.**

**Files:**
- Create: `windows/win_ai.py`
- Test: `tests/test_win_ai.py`

**Interfaces:**
- Consumes: `brain.diagnose(include_cleanup=False)` (Task 2), `i18n.tr` 새 키 (Task 3), `apppaths.user_data_dir()` (Task 1)
- Produces:
  - `win_ai.diagnosis_lines(language: str) -> list[str]` — 결과창에 그대로 뿌릴 줄 목록. **마지막 줄은 항상 삭제 경고**
  - `win_ai.api_key_missing_message(language: str) -> tuple[str, str]` — (제목, 본문). 본문에 `.env` 경로가 들어간다
  - `win_ai.has_api_key() -> bool`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_win_ai.py
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "windows"))

import brain
import win_ai


class DiagnosisLinesTests(unittest.TestCase):
    FAKE = {
        "why_slow": ["램이 거의 찼습니다.", "크롬이 4GB 를 쓰고 있어요."],
        "one_line_advice": "탭을 좀 닫아 보세요.",
        "recommendations": [],
        "estimated_bytes": 0,
    }

    def test_it_asks_for_a_diagnosis_without_cleanup(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE) as d:
            win_ai.diagnosis_lines("ko")
        self.assertEqual(d.call_args.kwargs["include_cleanup"], False)

    def test_the_explanation_and_the_advice_are_both_shown(self):
        with patch.object(win_ai.brain, "diagnose", return_value=self.FAKE):
            lines = win_ai.diagnosis_lines("ko")
        joined = "\n".join(lines)
        self.assertIn("램이 거의 찼습니다.", joined)
        self.assertIn("탭을 좀 닫아 보세요.", joined)

    def test_the_delete_warning_is_always_the_last_line(self):
        for language in ("ko", "en"):
            with self.subTest(language=language), \
                 patch.object(win_ai.brain, "diagnose", return_value=self.FAKE):
                lines = win_ai.diagnosis_lines(language)
            self.assertEqual(lines[-1], win_ai.i18n.tr(language,
                                                      "windows_delete_warning"))

    def test_it_never_reaches_the_file_deleting_code(self):
        """윈도우판은 지우지 않는다. 정리 코드에 발도 들이면 안 된다."""
        with patch.object(win_ai.brain, "collect_cleanup_candidates") as scan, \
             patch.object(win_ai.brain, "safe_trash") as trash, \
             patch.object(win_ai.brain, "_load_api_key", return_value=None):
            win_ai.diagnosis_lines("ko")
        scan.assert_not_called()
        trash.assert_not_called()


class ApiKeyMessageTests(unittest.TestCase):
    def test_the_message_names_the_env_file(self):
        title, body = win_ai.api_key_missing_message("ko")
        self.assertTrue(title.strip())
        self.assertIn(".env", body)
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/bin/python -m pytest tests/test_win_ai.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'win_ai'`

- [ ] **Step 3: 구현**

```python
# windows/win_ai.py
"""윈도우판 AI 기능의 **Qt 없는** 부분.

맥 개발 환경에는 PySide6 가 없어서 Qt 를 import 하면 테스트가 못 돈다.
무엇을 보여줄지 정하는 일은 전부 여기서 하고, ``win_ai_ui`` 는 그 결과를
창에 얹기만 한다.

**이 파일은 파일을 지우지 않는다.** ``brain.safe_trash`` 도,
``collect_cleanup_candidates`` 도 부르지 않는다. 윈도우에는 되돌릴 수 있는
휴지통 API 가 없고, 캐시 폴더가 프로필 폴더 안쪽에 있어서 목록을 그대로
옮길 수도 없다. 설명만 한다.
"""

import apppaths
import brain
import i18n


def has_api_key() -> bool:
    return bool(brain._load_api_key())


def api_key_missing_message(language):
    path = apppaths.user_data_dir() / ".env"
    return (
        i18n.tr(language, "no_api_key_title"),
        i18n.tr(language, "no_api_key_body", path=str(path)),
    )


def diagnosis_lines(language):
    """결과창에 그대로 뿌릴 줄 목록. 마지막 줄은 **항상** 삭제 경고다."""
    result = brain.diagnose(language=language, include_cleanup=False)
    lines = list(result.get("why_slow", []))
    advice = result.get("one_line_advice")
    if advice:
        lines.append("")
        lines.append(advice)
    lines.append("")
    lines.append(i18n.tr(language, "windows_delete_warning"))
    return lines
```

- [ ] **Step 4: 통과 확인**

Run: `./.venv/bin/python -m pytest tests/test_win_ai.py -v`

- [ ] **Step 5: 변형 감사 — 검사가 헛돌지 않는지**

경고 줄을 일부러 빼 보고 `test_the_delete_warning_is_always_the_last_line` 이 실패하는지 확인한다. 실패하지 않으면 검사가 가짜다.

- [ ] **Step 6: 커밋**

```bash
git add windows/win_ai.py tests/test_win_ai.py
git commit -m "feat: 윈도우 진단의 순수 로직"
```

---

### Task 6: 커스텀 테마 — 순수 로직

**Files:**
- Modify: `windows/win_ai.py`
- Test: `tests/test_win_ai.py`

**Interfaces:**
- Produces:
  - `win_ai.theme_target_dir() -> Path` — 새 테마가 저장될 폴더 (`apppaths.user_frames_dir()`)
  - `win_ai.check_photo(path) -> Optional[str]` — 문제가 있으면 보여줄 문구, 괜찮으면 `None`
  - `win_ai.create_theme(photo_path, name, language) -> str` — 만들어진 테마 이름. 실패하면 `ThemeError`. 안쪽에서 `vision_theme.build_theme(photo_path, theme_name, quality="medium") -> dict` 을 부른다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
# tests/test_win_ai.py 에 추가
class PhotoCheckTests(unittest.TestCase):
    def test_heic_is_refused_with_a_clear_message(self):
        """맥은 OS 해독기로 HEIC 를 열지만 윈도우는 못 연다.
        아이폰 사진이 기본 HEIC 라 그냥 실패하면 사용자가 이유를 모른다."""
        message = win_ai.check_photo(Path("cat.heic"))
        self.assertIsNotNone(message)
        self.assertIn("PNG", message)

    def test_png_jpeg_webp_pass(self):
        for name in ("cat.png", "cat.jpg", "cat.jpeg", "cat.webp"):
            with self.subTest(name=name):
                self.assertIsNone(win_ai.check_photo(Path(name)))


class ThemeTargetTests(unittest.TestCase):
    def test_new_themes_go_to_user_data_not_next_to_the_exe(self):
        """exe 옆에 쓰면 Program Files 에 깔렸을 때 권한이 없어 실패한다."""
        self.assertEqual(win_ai.theme_target_dir(), apppaths.user_frames_dir())
```

- [ ] **Step 2: 실패 확인**

Run: `./.venv/bin/python -m pytest tests/test_win_ai.py -k "Photo or ThemeTarget" -v`

- [ ] **Step 3: 구현**

```python
# windows/win_ai.py 에 추가
from pathlib import Path

import vision_theme

SUPPORTED_PHOTO_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class ThemeError(Exception):
    pass


def theme_target_dir():
    return apppaths.user_frames_dir()


def check_photo(path, language="ko"):
    """열 수 없는 형식이면 보여줄 문구를, 괜찮으면 None 을 돌려준다."""
    if Path(path).suffix.lower() not in SUPPORTED_PHOTO_SUFFIXES:
        return i18n.tr(language, "theme_error_format")
    return None


def create_theme(photo_path, name, language="ko"):
    """``vision_theme.build_theme`` 을 감싸 오류 문구를 한 자리로 모은다.

    이름이 비슷하지만 다른 함수다 — 이쪽은 윈도우 UI 가 쓰는 껍데기고,
    실제 생성은 ``vision_theme.build_theme`` 이 한다.
    """
    problem = check_photo(photo_path, language)
    if problem:
        raise ThemeError(problem)
    try:
        vision_theme.build_theme(Path(photo_path), name, quality="medium")
    except Exception as error:          # 네트워크·API·이미지 오류를 한 자리로
        raise ThemeError(str(error)) from error
    return name
```

> **확인함:** `vision_theme.build_theme(photo_path, theme_name, quality=...)` 이 실제 진입점이고 `dict` 를 돌려준다(`vision_theme.py:286`). 테마가 저장되는 곳은 `vision_theme.FRAMES_DIR` 인데 이 값은 **모듈을 읽을 때 `apppaths` 로 한 번 정해진다.** 그래서 Task 1 이 먼저 들어가야 윈도우에서 올바른 폴더에 쓴다. Task 6 의 `theme_target_dir()` 검사가 이걸 지킨다.

- [ ] **Step 4: 통과 확인 + 맥 전체 회귀**

Run: `./.venv/bin/python -m pytest tests -q`

- [ ] **Step 5: 커밋**

```bash
git add windows/win_ai.py tests/test_win_ai.py
git commit -m "feat: 윈도우 커스텀 테마의 순수 로직"
```

---

### Task 7: Qt 대화상자와 메뉴 붙이기

여기부터는 **맥에서 테스트할 수 없다.** 그래서 로직을 위에 다 빼 두었다. 이 파일은 얇게 유지한다.

**Files:**
- Create: `windows/win_ai_ui.py`
- Modify: `windows/windows_cat.pyw:299-328` (`contextMenuEvent`)

**Interfaces:**
- Consumes: `win_ai.diagnosis_lines`, `win_ai.api_key_missing_message`, `win_ai.has_api_key`, `win_ai.create_theme`, `win_ai.check_photo`
- Produces: `win_ai_ui.show_diagnosis(parent, language)`, `win_ai_ui.make_theme(parent, language, on_done)`

- [ ] **Step 1: `win_ai_ui.py` 를 쓴다**

```python
# windows/win_ai_ui.py
"""PySide6 대화상자. **판단은 하지 않는다** — win_ai 가 정한 것을 띄우기만.

맥 개발 환경에는 PySide6 가 없어 이 파일은 테스트가 안 돈다. 그래서 조건문을
여기 두면 아무도 검사하지 못한다. 새 규칙이 생기면 win_ai 에 넣는다.
"""

from PySide6 import QtCore, QtWidgets

import i18n
import win_ai


def show_diagnosis(parent, language):
    if not win_ai.has_api_key():
        title, body = win_ai.api_key_missing_message(language)
        QtWidgets.QMessageBox.information(parent, title, body)
        return
    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        lines = win_ai.diagnosis_lines(language)
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()
    QtWidgets.QMessageBox.information(
        parent, i18n.tr(language, "diagnosis_title"), "\n".join(lines))


class _ThemeWorker(QtCore.QThread):
    """생성은 1~2 분 걸린다. UI 스레드에서 돌리면 앱이 얼어붙는다."""
    finished_ok = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, photo, name, language):
        super().__init__()
        self._photo, self._name, self._language = photo, name, language

    def run(self):
        try:
            self.finished_ok.emit(
                win_ai.create_theme(self._photo, self._name, self._language))
        except Exception as error:
            self.failed.emit(str(error))


def make_theme(parent, language, on_done):
    if not win_ai.has_api_key():
        title, body = win_ai.api_key_missing_message(language)
        QtWidgets.QMessageBox.information(parent, title, body)
        return None

    photo, _ = QtWidgets.QFileDialog.getOpenFileName(
        parent, i18n.tr(language, "menu_make_theme"), "",
        "Images (*.png *.jpg *.jpeg *.webp)")
    if not photo:
        return None

    problem = win_ai.check_photo(photo, language)
    if problem:
        QtWidgets.QMessageBox.warning(parent, i18n.tr(language, "menu_make_theme"),
                                      problem)
        return None

    agreed = QtWidgets.QMessageBox.question(
        parent, i18n.tr(language, "theme_consent_title"),
        i18n.tr(language, "theme_consent_body"))
    if agreed != QtWidgets.QMessageBox.Yes:
        return None

    QtWidgets.QMessageBox.information(parent, i18n.tr(language, "menu_make_theme"),
                                      i18n.tr(language, "theme_working"))
    worker = _ThemeWorker(photo, "mypet", language)
    worker.finished_ok.connect(on_done)
    worker.failed.connect(
        lambda message: QtWidgets.QMessageBox.warning(
            parent, i18n.tr(language, "menu_make_theme"), message))
    worker.start()
    return worker          # 참조를 잡아 두지 않으면 GC 가 스레드를 죽인다
```

- [ ] **Step 2: 메뉴에 항목 두 개를 넣는다**

`windows/windows_cat.pyw` 의 `contextMenuEvent`, `menu_refresh` 바로 위:

```python
        menu.addSeparator()
        menu.addAction(tr(language, "menu_diagnose"),
                       lambda: win_ai_ui.show_diagnosis(self, language))
        menu.addAction(tr(language, "menu_make_theme"),
                       lambda: self._start_theme(language))
```

그리고 스레드 참조를 잡아 두는 자리:

```python
    def _start_theme(self, language):
        # 지역 변수로 두면 GC 가 스레드를 거둬 가서 생성이 조용히 멈춘다.
        self._theme_worker = win_ai_ui.make_theme(
            self, language, self._apply_new_theme)

    def _apply_new_theme(self, name):
        self.cfg["theme"] = name
        save_config(self.cfg)
        self.refresh()
```

- [ ] **Step 3: 빌드 스크립트에 새 모듈을 넣는다**

`windows/build_exe.bat` 에 `--hidden-import win_ai --hidden-import win_ai_ui` 추가.
Task 4 의 `ROOT_MODULES_THE_WINDOWS_APP_IMPORTS` 에도 두 이름을 더하고 테스트를 다시 돌린다.

- [ ] **Step 4: 맥 전체 회귀**

Run: `./.venv/bin/python -m pytest tests -q`
Expected: 전부 통과 (Qt 파일은 import 되지 않는다)

- [ ] **Step 5: 커밋**

```bash
git add windows/win_ai_ui.py windows/windows_cat.pyw windows/build_exe.bat tests/test_windows_build_script.py
git commit -m "feat: 윈도우 우클릭 메뉴에 진단과 테마 만들기를 넣는다"
```

---

### Task 8: 실기 검증 (회사 윈도우 PC + 친구 PC)

**여기가 이 계획에서 제일 중요한 단계다.** 지금까지의 테스트는 전부 맥에서 도는 것이고, Qt 코드는 한 줄도 실행된 적이 없다.

- [ ] **Step 1: exe 를 굽는다**

`windows/build_exe.bat` 를 윈도우에서 실행하거나, GitHub Actions 의 **Build Windows app** 을 `workflow_dispatch` 로 돌려 아티팩트를 받는다.

- [ ] **Step 2: 크기를 기록한다**

지금 52.9MB 다. 늘어난 값을 적어 둔다. (raw 로는 `numpy` 56M + `openai` 19M + `Pillow` 14M + `pydantic` 8M ≈ 98M 이 더해지지만, 맥 릴리스가 이걸 전부 넣고도 zip 39MB 인 걸 보면 실제 증가는 훨씬 작다. **구워 봐야 아는 값이다.**)

- [ ] **Step 3: 키 없이 먼저 연다**

`OPENAI_API_KEY` 없이 실행한다.
- 고양이가 뜨고 우클릭 메뉴가 전부 보이는가
- 진단을 누르면 "키가 필요해요" 안내가 뜨는가 (죽지 않는가)
- 테마 만들기도 같은 안내가 뜨는가
- **정보창이 비어 있지 않은가** (문구 키를 빠뜨리면 통째로 빈다)

- [ ] **Step 4: 키를 넣고 진단**

`%APPDATA%\Memory Cat\.env` 에 `OPENAI_API_KEY=...`
- 진단 결과가 나오는가
- **마지막 줄에 삭제 경고가 있는가**
- 결과 안에 "지워 드릴까요" 같은 제안이 **없는가**

- [ ] **Step 5: 테마 만들기**

- 사진 고르기 창이 뜨는가
- 동의 창이 먼저 뜨는가 (동의 전에 업로드되면 안 된다)
- 1~2분 동안 앱이 얼지 않는가
- 끝나면 새 테마가 적용되는가
- `%APPDATA%\Memory Cat\frames\mypet\` 에 `cat_00.png` ~ `cat_39.png` 가 있는가
- HEIC 사진을 고르면 "PNG, JPEG, WebP 만 됩니다" 가 뜨는가

- [ ] **Step 6: 재시작 후에도 남아 있는가**

앱을 껐다 켜서 만든 테마가 그대로인지 본다.

- [ ] **Step 7: 친구 PC 에서 3~6 을 한 번 더**

내 PC 에만 있는 조건(파이썬 설치, 권한 등) 때문에 되는 건 아닌지 본다.

- [ ] **Step 8: 결과를 이슈에 적는다**

크기, 걸린 시간, 안 된 것. 안 된 게 있으면 여기서 멈추고 고친다.

---

### Task 9: 문서

**Files:**
- Modify: `README.md:183`, `README.md` Privacy 섹션, `windows/README.txt`

- [ ] **Step 1: 다운로드 표의 윈도우 줄**

지금: `x64. No AI features — and no network requests at all`
→ `x64. Diagnosis and custom pet themes are optional and need your own OpenAI key; without one the app makes no network requests.`

- [ ] **Step 2: Privacy 섹션**

"The Windows build has no OpenAI dependency and makes no network requests at all" 를 맥과 같은 방식으로 고친다 — **키가 없으면 네트워크를 쓰지 않는다.** 그리고 **윈도우판은 파일을 지우지 않는다**는 문장을 새로 넣는다. 이건 맥보다 나은 점이 아니라 **다른 점**이므로 이유까지 적는다(되돌릴 수 있는 휴지통 API 가 없음).

- [ ] **Step 3: `windows/README.txt`**

`.env` 위치(`%APPDATA%\Memory Cat\.env`)와 두 기능이 선택 사항이라는 것.

- [ ] **Step 4: 커밋**

```bash
git add README.md windows/README.txt
git commit -m "docs: 윈도우판이 무엇을 하고 무엇을 안 하는지 고쳐 적는다"
```

---

## 이 계획이 일부러 안 하는 것

| 안 함 | 이유 |
|---|---|
| 윈도우 파일 정리 | 되돌릴 수 있는 휴지통 API 가 표준에 없고, 캐시가 프로필 폴더 안쪽이라 목록을 그대로 못 옮긴다. 경고 문구로 대신한다 |
| HEIC 지원 (`pillow-heif`) | 의존성이 하나 더 는다. 먼저 "안 된다"고 **분명히 말하는 것**까지만. 실기에서 아이폰 사진이 얼마나 걸리는지 보고 정한다 |
| `config.json` 위치 옮기기 | 지금 윈도우판은 exe 옆에 둔다. 옮기면 기존 사용자 설정 이사가 필요하다. 새 기능이 먼저다 |
| 윈도우 그림 매핑 (#40) | 별건. 이 계획과 섞으면 무엇 때문에 화면이 바뀌었는지 알 수 없게 된다 |
| 반올림 어긋남 | 0.5%p 창. #40 에 기록됨 |
| v0.4.0 발행 | 머지 다 되고 실기 검증 끝난 뒤 별도로 |

## 순서와 병렬

```
Task 1 (apppaths) ─┐
Task 2 (brain)    ─┼→ Task 5 (진단 로직) ─┐
Task 3 (문구)     ─┘                      ├→ Task 7 (Qt UI) → Task 8 (실기) → Task 9 (문서)
Task 4 (빌드)     ────→ Task 6 (테마 로직) ┘
```

Task 1~4 는 서로 독립이라 순서 상관없다. Task 8 에서 막히면 그 앞으로 돌아간다.
