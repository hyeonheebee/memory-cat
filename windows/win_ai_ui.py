"""PySide6 대화상자. **판단은 하지 않는다** — win_ai 가 정한 것을 띄우기만.

맥 개발 환경에는 PySide6 가 없어 이 파일은 테스트가 안 돈다. 그래서 조건문을
여기 두면 아무도 검사하지 못한다. 새 규칙이 생기면 win_ai 에 넣는다.

스레드 규칙 두 가지:

* 워커의 ``run()`` 안에서는 Qt 위젯을 절대 만지지 않는다. 결과는 시그널로만
  내보낸다.
* 워커 시그널을 lambda·일반 함수에 이을 때는 ``QueuedConnection`` 을 명시한다.
  그래야 메시지 상자가 반드시 GUI 스레드에서 뜬다. 자동 연결에 맡기면 받는 쪽이
  QObject 가 아닐 때 PySide6 버전에 따라 워커 스레드에서 바로 불릴 수 있다.
"""

from PySide6 import QtCore, QtWidgets

import win_ai
from i18n import tr

#: 파일 고르기 창의 형식 필터. 사용자에게 보이는 문장이 아니라 Qt 문법이다.
IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"


def _queued():
    return QtCore.Qt.ConnectionType.QueuedConnection


def _explain_missing_key(parent, language):
    title, body = win_ai.api_key_missing_message(language)
    QtWidgets.QMessageBox.information(parent, title, body)


class _DiagnosisWorker(QtCore.QThread):
    """``brain.diagnose`` 는 OpenAI 타임아웃 20초·재시도 1회라 수십 초 걸릴 수
    있다. UI 스레드에서 부르면 그동안 고양이가 얼어붙는다."""

    finished_ok = QtCore.Signal(object)     # 줄 목록(list[str])
    failed = QtCore.Signal(str)

    def __init__(self, language):
        super().__init__()
        self._language = language

    def run(self):
        try:
            lines = win_ai.diagnosis_lines(self._language)
        except Exception as error:
            # 원문은 로그로만 보낸다 — 로그 함수 자체는 예외를 내지 않으므로
            # 워커 스레드에서 새 예외가 생길 걱정은 없다.
            win_ai.log_ai_failure("diagnosis", error)
            self.failed.emit(str(error))
            return
        self.finished_ok.emit(lines)


class _ThemeWorker(QtCore.QThread):
    """생성은 1~2 분 걸린다. UI 스레드에서 돌리면 앱이 얼어붙는다."""

    finished_ok = QtCore.Signal(str)        # 만든 테마 이름
    failed = QtCore.Signal(str)

    def __init__(self, photo, name, language):
        super().__init__()
        self._photo, self._name, self._language = photo, name, language

    def run(self):
        try:
            name = win_ai.create_theme(self._photo, self._name, self._language)
        except Exception as error:
            # create_theme 이 내는 ThemeError 는 이미 번역된 메시지다. 그 밖의
            # (있어선 안 되는) 예외가 새 나오면 원문 대신 일반 안내로 감춘다
            # — 판단은 win_ai.theme_failure_message 가, 여기서는 결과만 emit.
            if not isinstance(error, win_ai.ThemeError):
                win_ai.log_ai_failure("theme", error)
            self.failed.emit(win_ai.theme_failure_message(error, self._language))
            return
        self.finished_ok.emit(name)


def _show_diagnosis(parent, language, lines):
    QtWidgets.QMessageBox.information(
        parent, tr(language, "diagnosis_title"), "\n".join(lines))


def _show_diagnosis_failure(parent, language, message):
    # 원문(message)은 화면에 붙이지 않는다 — 로그(win_ai.log_ai_failure)로만
    # 보낸다. 여기서는 번역된 안내 한 줄만 보여준다.
    QtWidgets.QMessageBox.warning(
        parent, tr(language, "diagnosis_title"), tr(language, "diagnosis_error"))


def show_diagnosis(parent, language):
    """진단을 워커 스레드에서 시작하고 워커를 돌려준다. 키가 없으면 ``None``.

    호출부는 돌려받은 워커를 붙잡고 있어야 한다. 지역 변수로 두면 GC 가 도는
    스레드를 거둬 가서 앱이 죽는다.
    """
    if not win_ai.has_api_key():
        _explain_missing_key(parent, language)
        return None

    worker = _DiagnosisWorker(language)
    worker.finished_ok.connect(
        lambda lines: _show_diagnosis(parent, language, lines), _queued())
    worker.failed.connect(
        lambda message: _show_diagnosis_failure(parent, language, message),
        _queued())
    worker.start()
    return worker


def _show_theme_failure(parent, language, message):
    QtWidgets.QMessageBox.warning(
        parent, tr(language, "pet_theme_error_title"), message)


def make_theme(parent, language, bundled_frames_dir, on_done):
    """사진을 골라 테마 생성을 워커 스레드에서 시작하고 워커를 돌려준다.

    중간에 그만두면(키 없음·취소·형식 오류·동의 안 함) ``None``.
    ``on_done(name)`` 은 GUI 스레드에서 불린다.
    """
    if not win_ai.has_api_key():
        _explain_missing_key(parent, language)
        return None

    photo, _ = QtWidgets.QFileDialog.getOpenFileName(
        parent, tr(language, "menu_pet_theme"), "", IMAGE_FILTER)
    if not photo:
        return None

    problem = win_ai.check_photo(photo, language)
    if problem:
        QtWidgets.QMessageBox.warning(parent, tr(language, "menu_pet_theme"), problem)
        return None

    answer = QtWidgets.QMessageBox.question(
        parent,
        tr(language, "pet_theme_consent_title"),
        tr(language, "pet_theme_consent_body"))
    if answer != QtWidgets.QMessageBox.StandardButton.Yes:
        return None

    # 기본 테마·이미 만든 테마와 겹치지 않는 이름(mypet, mypet2, ...).
    # vision_theme 은 있는 폴더를 덮어쓰지 않으므로 고정 이름을 쓰면 두 번째부터 실패한다.
    name = win_ai.next_theme_name(bundled_frames_dir)

    # 안내창은 모달이라 사용자가 닫을 때까지 여기서 멈춘다. 스레드를 시작하기
    # **전에** 띄운다 — 시작한 뒤에 띄우면 이 창에서 예외가 났을 때 도는 워커를
    # 아무도 붙잡지 않은 채 GC 에 넘기게 된다.
    QtWidgets.QMessageBox.information(
        parent, tr(language, "menu_pet_theme"), tr(language, "theme_working"))

    worker = _ThemeWorker(photo, name, language)
    worker.finished_ok.connect(on_done, _queued())
    worker.failed.connect(
        lambda message: _show_theme_failure(parent, language, message), _queued())
    worker.start()
    return worker          # 참조를 잡아 두지 않으면 GC 가 스레드를 죽인다
